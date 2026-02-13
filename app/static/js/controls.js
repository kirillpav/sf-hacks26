/**
 * Bbox drawer and form controls for the deforestation alert dashboard.
 */

const Controls = (() => {
    let drawnBbox = null;
    let drawLayer = null;
    let drawControl = null;

    function init(map) {
        drawLayer = new L.FeatureGroup();
        map.addLayer(drawLayer);

        drawControl = new L.Control.Draw({
            draw: {
                rectangle: {
                    shapeOptions: {
                        color: '#e94560',
                        weight: 2,
                        fillOpacity: 0.1,
                    },
                },
                polygon: false,
                polyline: false,
                circle: false,
                marker: false,
                circlemarker: false,
            },
            edit: {
                featureGroup: drawLayer,
            },
        });
        map.addControl(drawControl);

        map.on(L.Draw.Event.CREATED, (e) => {
            drawLayer.clearLayers();
            drawLayer.addLayer(e.layer);
            const bounds = e.layer.getBounds();
            drawnBbox = [
                parseFloat(bounds.getWest().toFixed(4)),
                parseFloat(bounds.getSouth().toFixed(4)),
                parseFloat(bounds.getEast().toFixed(4)),
                parseFloat(bounds.getNorth().toFixed(4)),
            ];
            updateBboxDisplay(drawnBbox);
        });

        map.on(L.Draw.Event.DELETED, () => {
            drawnBbox = null;
            updateBboxDisplay(null);
        });
    }

    function updateBboxDisplay(bbox) {
        const el = document.getElementById('bbox-display');
        if (bbox) {
            el.textContent = `[${bbox.join(', ')}]`;
            el.style.color = '#e0e0e0';
        } else {
            el.textContent = 'No area selected';
            el.style.color = '#8899aa';
        }
    }

    function getBbox() {
        return drawnBbox;
    }

    function clearDraw() {
        if (drawLayer) drawLayer.clearLayers();
        drawnBbox = null;
        updateBboxDisplay(null);
    }

    function getFormData() {
        return {
            region_name: document.getElementById('region-input').value.trim() || null,
            bbox: drawnBbox,
            before_start: document.getElementById('before-start').value || null,
            before_end: document.getElementById('before-end').value || null,
            after_start: document.getElementById('after-start').value || null,
            after_end: document.getElementById('after-end').value || null,
        };
    }

    function setDefaultDates() {
        const now = new Date();
        const fmt = (d) => d.toISOString().split('T')[0];
        const ago = (days) => new Date(now.getTime() - days * 86400000);

        document.getElementById('before-start').value = fmt(ago(365));
        document.getElementById('before-end').value = fmt(ago(180));
        document.getElementById('after-start').value = fmt(ago(90));
        document.getElementById('after-end').value = fmt(now);
    }

    return { init, getBbox, clearDraw, getFormData, setDefaultDates };
})();
