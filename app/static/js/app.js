/**
 * Main application — Leaflet map + API interaction for deforestation alerts.
 */

const App = (() => {
    let map;
    let patchesLayer;
    let firesLayer;
    let currentAlertId = null;
    let pollInterval = null;
    let lastFailedAlertId = null;
    let currentGeojson = null;
    let currentBbox = null;

    const SEVERITY_COLORS = {
        HIGH: '#e94560',
        MEDIUM: '#f39c12',
        LOW: '#f1c40f',
    };

    // Default view: Rondonia, Brazil
    const DEFAULT_CENTER = [-10.25, -62.5];
    const DEFAULT_ZOOM = 9;

    function initMap() {
        map = L.map('map').setView(DEFAULT_CENTER, DEFAULT_ZOOM);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 18,
        }).addTo(map);

        // Satellite imagery layer
        const satellite = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {
                attribution: '&copy; Esri',
                maxZoom: 18,
            }
        );

        L.control.layers(
            { 'Street Map': map._layers[Object.keys(map._layers)[0]], 'Satellite': satellite },
            {},
            { position: 'topright' }
        ).addTo(map);

        patchesLayer = L.geoJSON(null, {
            style: (feature) => ({
                color: SEVERITY_COLORS[feature.properties.severity] || '#e94560',
                weight: 2,
                fillOpacity: 0.35,
                fillColor: SEVERITY_COLORS[feature.properties.severity] || '#e94560',
            }),
            onEachFeature: (feature, layer) => {
                const p = feature.properties;
                layer.bindPopup(`
                    <div class="popup-title severity-${p.severity}">${p.severity} Severity</div>
                    <div class="popup-row"><span class="popup-label">Area:</span> ${p.area_hectares} ha</div>
                    <div class="popup-row"><span class="popup-label">NDVI Drop:</span> ${p.ndvi_drop}</div>
                    <div class="popup-row"><span class="popup-label">Confidence:</span> ${(p.confidence * 100).toFixed(0)}%</div>
                    <div class="popup-row"><span class="popup-label">Location:</span> ${p.centroid[0].toFixed(4)}, ${p.centroid[1].toFixed(4)}</div>
                `);
            },
        }).addTo(map);

        firesLayer = L.layerGroup().addTo(map);

        addLegend();
        Controls.init(map);
        Controls.setDefaultDates();
    }

    function addLegend() {
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = () => {
            const div = L.DomUtil.create('div', 'leaflet-legend');
            div.innerHTML = `
                <div class="legend-title">Severity</div>
                <div class="legend-item"><span class="legend-color" style="background:#e94560"></span> HIGH</div>
                <div class="legend-item"><span class="legend-color" style="background:#f39c12"></span> MEDIUM</div>
                <div class="legend-item"><span class="legend-color" style="background:#f1c40f"></span> LOW</div>
            `;
            return div;
        };
        legend.addTo(map);
    }

    function bindEvents() {
        document.getElementById('analyze-btn').addEventListener('click', startAnalysis);
        document.getElementById('demo-btn').addEventListener('click', loadDemo);
        document.getElementById('clear-btn').addEventListener('click', clearResults);
        document.getElementById('retry-btn').addEventListener('click', retryAnalysis);
        document.getElementById('download-geojson-btn').addEventListener('click', downloadGeoJSON);
        document.getElementById('show-fires-checkbox').addEventListener('change', toggleFires);

        // Check mode
        fetch('/api/health')
            .then((r) => r.json())
            .then((data) => {
                const badge = document.getElementById('mode-badge');
                if (data.demo_mode) {
                    badge.textContent = 'DEMO';
                    badge.classList.remove('live');
                } else {
                    badge.textContent = 'LIVE';
                    badge.classList.add('live');
                }
            });

        loadAlertHistory();
        showFirstVisitPrompt();
    }

    function showFirstVisitPrompt() {
        const seen = sessionStorage.getItem('deforest-seen');
        if (!seen && document.getElementById('alerts-list').querySelector('.muted')) {
            const hint = document.createElement('p');
            hint.className = 'demo-hint muted';
            hint.textContent = 'Tip: Click "Load Demo" to see a quick example.';
            hint.style.marginTop = '8px';
            document.getElementById('analysis-panel').appendChild(hint);
            sessionStorage.setItem('deforest-seen', '1');
        }
    }

    function retryAnalysis() {
        if (!lastFailedAlertId) return;
        const formData = Controls.getFormData();
        if (formData.bbox || formData.region_name) {
            document.getElementById('retry-area').style.display = 'none';
            submitAnalysis(formData);
        }
    }

    function downloadGeoJSON() {
        if (!currentGeojson) return;
        const blob = new Blob([JSON.stringify(currentGeojson, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `deforestation-alert-${currentGeojson.properties?.alert_id || 'export'}.geojson`;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    function setFireStatus(msg, isError = false) {
        const el = document.getElementById('fires-status');
        el.textContent = msg;
        el.className = 'fires-status ' + (isError ? 'fires-error' : 'muted');
    }

    function getBboxForFires() {
        if (currentBbox && currentBbox.length === 4) return currentBbox;
        // Fallback: use patches layer bounds if we have features
        const features = patchesLayer.getLayers?.();
        if (features?.length > 0) {
            try {
                const bounds = patchesLayer.getBounds();
                if (bounds) return [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()];
            } catch (_) {}
        }
        return null;
    }

    function toggleFires() {
        const checked = document.getElementById('show-fires-checkbox').checked;
        firesLayer.clearLayers();
        setFireStatus('');
        if (!checked) return;
        const bbox = getBboxForFires();
        if (!bbox) {
            setFireStatus('Run an analysis first', true);
            return;
        }
        const [west, south, east, north] = bbox;
        setFireStatus('Loading...');
        fetch(`/api/fires?west=${west}&south=${south}&east=${east}&north=${north}&days=5`)
            .then((r) => {
                if (!r.ok) throw new Error('Request failed');
                return r.json();
            })
            .then((data) => {
                if (!data.configured) {
                    setFireStatus('NASA FIRMS key not configured', true);
                    return;
                }
                const points = data.points || [];
                points.forEach((p) => {
                    L.circleMarker([p.lat, p.lon], {
                        radius: 5,
                        fillColor: '#ff6b35',
                        color: '#fff',
                        weight: 1,
                        fillOpacity: 0.8,
                    }).addTo(firesLayer);
                });
                if (points.length === 0) {
                    setFireStatus('No hotspots in last 5 days');
                } else {
                    setFireStatus(`${points.length} hotspot${points.length !== 1 ? 's' : ''}`);
                }
            })
            .catch((e) => {
                console.warn('Fire fetch failed:', e);
                setFireStatus('Failed to load', true);
            });
    }

    function loadDemo() {
        // Set Rondonia bbox and submit
        document.getElementById('region-input').value = '';
        const demoRequest = {
            bbox: [-63.0, -10.5, -62.0, -10.0],
        };
        submitAnalysis(demoRequest);

        // Center map on demo area
        map.fitBounds([[-10.5, -63.0], [-10.0, -62.0]]);
    }

    function startAnalysis() {
        const formData = Controls.getFormData();
        if (!formData.bbox && !formData.region_name) {
            alert('Please draw a bounding box on the map or enter a region name.');
            return;
        }
        submitAnalysis(formData);
    }

    async function submitAnalysis(requestData) {
        const analyzeBtn = document.getElementById('analyze-btn');
        const demoBtn = document.getElementById('demo-btn');
        analyzeBtn.disabled = true;
        demoBtn.disabled = true;

        try {
            const resp = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData),
            });

            if (!resp.ok) {
                const err = await resp.json();
                alert(`Error: ${err.detail || 'Analysis failed'}`);
                analyzeBtn.disabled = false;
                demoBtn.disabled = false;
                return;
            }

            const data = await resp.json();
            currentAlertId = data.analysis_id;
            showProgress();
            startPolling(currentAlertId);
        } catch (e) {
            alert(`Request failed: ${e.message}`);
            analyzeBtn.disabled = false;
            demoBtn.disabled = false;
        }
    }

    function showProgress() {
        document.getElementById('progress-panel').style.display = 'block';
        document.getElementById('results-panel').style.display = 'none';
        document.getElementById('retry-area').style.display = 'none';
    }

    function startPolling(alertId) {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/analyze/${alertId}/status`);
                const data = await resp.json();

                updateProgress(data.progress, data.status);

                if (data.status === 'COMPLETED') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    document.getElementById('retry-area').style.display = 'none';
                    await showResults(alertId);
                } else if (data.status === 'FAILED') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    lastFailedAlertId = alertId;
                    document.getElementById('progress-text').textContent =
                        `Failed: ${data.error || 'Unknown error'}`;
                    document.getElementById('retry-area').style.display = 'block';
                    document.getElementById('analyze-btn').disabled = false;
                    document.getElementById('demo-btn').disabled = false;
                }
            } catch (e) {
                console.error('Polling error:', e);
            }
        }, 500);
    }

    function updateProgress(pct, status) {
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        fill.style.width = pct + '%';

        const labels = {
            PENDING: 'Queued...',
            RUNNING: `Processing... ${pct}%`,
            COMPLETED: 'Complete!',
            FAILED: 'Failed',
        };
        text.textContent = labels[status] || `${pct}%`;
    }

    async function showResults(alertId) {
        document.getElementById('progress-panel').style.display = 'none';
        document.getElementById('results-panel').style.display = 'block';
        document.getElementById('analyze-btn').disabled = false;
        document.getElementById('demo-btn').disabled = false;

        // Fetch GeoJSON
        const resp = await fetch(`/api/alerts/${alertId}/geojson`);
        const geojson = await resp.json();
        currentGeojson = geojson;
        const alertData = await fetch(`/api/alerts/${alertId}`).then((r) => r.json());
        currentBbox = geojson.features.length > 0 ? getBboxFromFeatures(geojson.features) : alertData.region;

        // Update stats
        document.getElementById('stat-patches').textContent = geojson.properties.patch_count;
        document.getElementById('stat-area').textContent = geojson.properties.total_area_hectares;

        // Scene metadata (LIVE mode)
        const sceneEl = document.getElementById('scene-metadata');
        if (geojson.properties.before_scene || geojson.properties.after_scene) {
            const before = geojson.properties.before_scene;
            const after = geojson.properties.after_scene;
            sceneEl.innerHTML = `
                <strong>Sentinel-2 scenes</strong><br>
                Before: ${before?.scene_id || '—'} (${before?.acquisition_date || '—'})<br>
                After: ${after?.scene_id || '—'} (${after?.acquisition_date || '—'})
            `;
            sceneEl.style.display = 'block';
        } else {
            sceneEl.style.display = 'none';
        }

        // Render patches on map
        patchesLayer.clearLayers();
        firesLayer.clearLayers();
        document.getElementById('show-fires-checkbox').checked = false;
        setFireStatus('');
        patchesLayer.addData(geojson);

        // Fit map to patches
        if (geojson.features.length > 0) {
            map.fitBounds(patchesLayer.getBounds().pad(0.1));
        } else if (currentBbox && currentBbox.length === 4) {
            map.fitBounds([[currentBbox[1], currentBbox[0]], [currentBbox[3], currentBbox[2]]]);
        }

        // Show NDVI comparison with slider
        const compEl = document.getElementById('ndvi-comparison');
        document.getElementById('ndvi-before').src = `/api/alerts/${alertId}/before.png`;
        document.getElementById('ndvi-after').src = `/api/alerts/${alertId}/after.png`;
        compEl.style.display = 'block';

        // Refresh alert history
        loadAlertHistory();
    }

    function getBboxFromFeatures(features) {
        let minLon = 180, minLat = 90, maxLon = -180, maxLat = -90;
        features.forEach((f) => {
            const coords = f.geometry?.coordinates?.[0] || [];
            coords.forEach(([lon, lat]) => {
                if (lon < minLon) minLon = lon;
                if (lat < minLat) minLat = lat;
                if (lon > maxLon) maxLon = lon;
                if (lat > maxLat) maxLat = lat;
            });
        });
        return [minLon, minLat, maxLon, maxLat];
    }

    function clearResults() {
        patchesLayer.clearLayers();
        firesLayer.clearLayers();
        document.getElementById('results-panel').style.display = 'none';
        document.getElementById('ndvi-comparison').style.display = 'none';
        document.getElementById('scene-metadata').style.display = 'none';
        document.getElementById('show-fires-checkbox').checked = false;
        setFireStatus('');
        currentGeojson = null;
        currentBbox = null;
        Controls.clearDraw();
    }

    async function loadAlertHistory() {
        try {
            const resp = await fetch('/api/alerts');
            const alerts = await resp.json();
            const list = document.getElementById('alerts-list');

            if (alerts.length === 0) {
                list.innerHTML = '<p class="muted">No alerts yet</p>';
                return;
            }

            list.innerHTML = alerts
                .reverse()
                .map(
                    (a) => `
                <div class="alert-item" data-id="${a.alert_id}">
                    <div class="alert-meta">
                        <span class="alert-patches">${a.patch_count} patches (${a.total_area_hectares} ha)</span>
                        <span class="alert-time">${new Date(a.timestamp).toLocaleTimeString()}</span>
                    </div>
                </div>
            `
                )
                .join('');

            // Click to load alert
            list.querySelectorAll('.alert-item').forEach((el) => {
                el.addEventListener('click', () => {
                    const id = el.dataset.id;
                    showResults(id);
                });
            });
        } catch (e) {
            console.error('Failed to load alerts:', e);
        }
    }

    // Init
    document.addEventListener('DOMContentLoaded', () => {
        initMap();
        bindEvents();
    });

    return { map };
})();
