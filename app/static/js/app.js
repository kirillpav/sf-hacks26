/**
 * Main application — Leaflet map + API interaction for deforestation alerts.
 */

const App = (() => {
    let map;
    let patchesLayer;
    let currentAlertId = null;
    let pollInterval = null;

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

        Controls.init(map);
        Controls.setDefaultDates();
    }

    function bindEvents() {
        document.getElementById('analyze-btn').addEventListener('click', startAnalysis);
        document.getElementById('demo-btn').addEventListener('click', loadDemo);
        document.getElementById('clear-btn').addEventListener('click', clearResults);

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
                    await showResults(alertId);
                } else if (data.status === 'FAILED') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    document.getElementById('progress-text').textContent =
                        `Failed: ${data.error || 'Unknown error'}`;
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

        // Update stats
        document.getElementById('stat-patches').textContent = geojson.properties.patch_count;
        document.getElementById('stat-area').textContent = geojson.properties.total_area_hectares;

        // Render patches on map
        patchesLayer.clearLayers();
        patchesLayer.addData(geojson);

        // Fit map to patches
        if (geojson.features.length > 0) {
            map.fitBounds(patchesLayer.getBounds().pad(0.1));
        }

        // Show NDVI images
        const imgContainer = document.getElementById('ndvi-images');
        document.getElementById('ndvi-before').src = `/api/alerts/${alertId}/before.png`;
        document.getElementById('ndvi-after').src = `/api/alerts/${alertId}/after.png`;
        imgContainer.style.display = 'flex';

        // Refresh alert history
        loadAlertHistory();
    }

    function clearResults() {
        patchesLayer.clearLayers();
        document.getElementById('results-panel').style.display = 'none';
        document.getElementById('ndvi-images').style.display = 'none';
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
