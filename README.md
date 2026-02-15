# Satellite Deforestation Alert System

Detect deforestation from free Sentinel-2 satellite imagery, estimate carbon impact, model restoration scenarios, and alert conservation organizations — all from a single web dashboard.

Built at **SF Hacks 2026**.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Sentinel-2](https://img.shields.io/badge/Data-Sentinel--2%20L2A-orange)

## What It Does

1. **You draw a bounding box** on an interactive map (or type a region name like "Rondonia, Brazil")
2. **The system fetches real Sentinel-2 satellite imagery** from two time periods via AWS Open Data (no API key needed)
3. **Computes NDVI change** (Normalized Difference Vegetation Index) to identify where vegetation was lost
4. **Classifies deforestation severity** (HIGH / MEDIUM / LOW) and extracts polygon patches
5. **Estimates carbon impact**: CO2 loss, trees needed to replant, recovery timeline
6. **Models "What-if" intervention scenarios**: natural regeneration vs. assisted planting vs. intensive restoration
7. **Generates a narrative briefing** ready to paste into NGO reports or social media
8. **Fires a webhook** to alert conservation organizations in real time
9. **Overlays NASA FIRMS fire hotspots** for additional context

## Quick Start

### Prerequisites

- Python 3.12+
- pip

### 1. Clone and install

```bash
git clone https://github.com/your-org/sf-hacks26.git
cd sf-hacks26
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `true` | Set to `false` for real satellite data |
| `WEBHOOK_URL` | _(empty)_ | URL to POST alert payloads to |
| `NASA_FIRMS_KEY` | _(empty)_ | Optional — get one free at [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/map_key/) for fire hotspot overlay |
| `NDVI_THRESHOLD_LOW` | `0.3` | NDVI drop threshold for LOW severity |
| `NDVI_THRESHOLD_MEDIUM` | `0.4` | NDVI drop threshold for MEDIUM severity |
| `NDVI_THRESHOLD_HIGH` | `0.5` | NDVI drop threshold for HIGH severity |
| `MIN_PATCH_HECTARES` | `1.0` | Ignore patches smaller than this |
| `MAX_BBOX_DEGREES` | `2.0` | Max bounding box size (auto-crops larger regions) |

### 3. Run the server

```bash
uvicorn app.main:app --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

### 4. Try it out

- **Demo mode** (`DEMO_MODE=true`): Click **"Load Demo"** to see synthetic deforestation patches over Rondonia, Brazil
- **Live mode** (`DEMO_MODE=false`): Draw a bounding box over a forested area or type a region name, then click **"Analyze"** — the system fetches real Sentinel-2 imagery from AWS

### Docker

```bash
docker compose up
```

The app runs at `http://localhost:8000`. A webhook tester is available at `http://localhost:8080`.

## How It Works

### Data Pipeline

```
User draws bbox on map
  -> POST /api/analyze
    -> Geocode region name to bbox (if needed)
    -> Search Earth Search STAC for Sentinel-2 L2A scenes
    -> Fetch Red (B04) + NIR (B08) bands from COGs on AWS S3
       (twice: "before" period and "after" period)
    -> Compute NDVI = (NIR - Red) / (NIR + Red) for both periods
    -> NDVI diff -> negative values = vegetation loss
    -> Classify severity (HIGH > 0.5 drop, MEDIUM > 0.4, LOW > 0.3)
    -> Vectorize to polygons, filter noise, compute area
    -> Estimate carbon loss, trees to replant, regrowth timeline
    -> Generate narrative briefing
    -> Fire webhook to configured URL
  <- Return alert with patches on map
```

### Satellite Data Source

- **Catalog**: [Earth Search STAC](https://earth-search.aws.element84.com/v1) (no API key required)
- **Collection**: Sentinel-2 L2A (atmospherically corrected)
- **Access**: Cloud-Optimized GeoTIFFs (COGs) read directly from AWS S3 with `AWS_NO_SIGN_REQUEST=YES`
- **Resolution**: Read at overview level 2 for speed (~40m effective resolution)
- **CRS handling**: Automatic reprojection from Sentinel-2 UTM to WGS84

### Carbon & Restoration Model

Uses IPCC Tier 1 carbon density defaults by biome (detected from latitude):

| Biome | Carbon Density | Tree Density | Base Recovery |
|-------|---------------|--------------|---------------|
| Tropical | 170 tC/ha | 400 trees/ha | 15 years |
| Temperate | 120 tC/ha | 300 trees/ha | 20 years |
| Boreal | 60 tC/ha | 200 trees/ha | 30 years |
| Savanna | 30 tC/ha | 80 trees/ha | 10 years |

Three intervention scenarios with different cost/speed tradeoffs:

| Scenario | Recovery Speed | Tree Survival | Cost/ha |
|----------|---------------|---------------|---------|
| Natural Regeneration | Baseline | 60% | $0 |
| Assisted Planting | 40% faster | 75% | $1,200 |
| Intensive Restoration | 65% faster | 88% | $3,500 |

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check, shows demo_mode status |
| `POST` | `/api/analyze` | Start analysis (returns 202 + analysis_id) |
| `GET` | `/api/analyze/{id}/status` | Poll progress (0-100%) |
| `GET` | `/api/alerts` | List all alerts |
| `GET` | `/api/alerts/{id}` | Full alert with patches and impact data |
| `GET` | `/api/alerts/{id}/geojson` | GeoJSON FeatureCollection for map rendering |
| `POST` | `/api/alerts/{id}/intervention` | Recompute impact under a different scenario |
| `GET` | `/api/alerts/{id}/before.png` | NDVI visualization (before) |
| `GET` | `/api/alerts/{id}/after.png` | NDVI visualization (after) |
| `GET` | `/api/fires` | NASA FIRMS fire hotspots for a bbox |
| `POST` | `/api/regions` | Save a monitored region |
| `GET` | `/api/regions` | List saved regions |

### Example: Start an analysis

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"bbox": [-63.0, -10.5, -62.0, -10.0]}'
```

### Example: Run a what-if intervention

```bash
curl -X POST http://localhost:8000/api/alerts/{alert_id}/intervention \
  -H 'Content-Type: application/json' \
  -d '{"intervention": "intensive_restoration"}'
```

### Webhook Payload

When `WEBHOOK_URL` is configured, every completed analysis POSTs:

```json
{
  "alert_id": "uuid",
  "timestamp": "2026-02-14T...",
  "region": [-63.0, -10.5, -62.0, -10.0],
  "patches": [...],
  "total_area_hectares": 35356.0,
  "patch_count": 8,
  "aggregate_impact": {
    "total_carbon_loss_tonnes": 3820832.1,
    "total_trees_to_replant": 23570691,
    "avg_regrowth_months": 322,
    "total_cost_estimate_usd": 0
  },
  "narrative": "Satellite analysis detected 8 deforestation patches..."
}
```

## Project Structure

```
sf-hacks26/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings from environment variables
│   ├── routers/
│   │   ├── analysis.py          # POST /api/analyze, GET status
│   │   ├── alerts.py            # Alerts, GeoJSON, intervention, fires
│   │   ├── regions.py           # Save/list monitored regions
│   │   └── health.py            # Health check
│   ├── services/
│   │   ├── imagery.py           # STAC search + COG band fetching
│   │   ├── ndvi.py              # NDVI computation, diff, classification
│   │   ├── patch_detector.py    # Raster -> polygon extraction
│   │   ├── carbon.py            # Carbon loss, trees, regrowth modeling
│   │   ├── storytelling.py      # Narrative briefing generation
│   │   ├── webhook.py           # Async webhook dispatch
│   │   ├── geocoder.py          # Region name -> bounding box
│   │   ├── firms.py             # NASA FIRMS fire hotspots
│   │   └── pipeline.py          # Orchestrates the full analysis flow
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── db.py                # In-memory data store
│   ├── static/                  # Frontend (Leaflet.js dashboard)
│   └── demo/
│       └── sample_data.py       # Synthetic NDVI for demo mode
├── tests/
│   ├── test_ndvi.py             # NDVI math tests
│   ├── test_patch_detector.py   # Patch extraction tests
│   └── test_api.py              # API endpoint tests
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Running Tests

```bash
pytest tests/ -v
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI, uvicorn
- **Raster processing**: rasterio, numpy, shapely, pyproj
- **Satellite search**: pystac-client (Earth Search STAC catalog)
- **Map UI**: Leaflet.js + Leaflet.draw (CDN)
- **Geocoding**: geopy (Nominatim, no API key)
- **Webhook**: httpx (async)
- **Visualization**: matplotlib
- **Containerization**: Docker + docker-compose

## License

MIT
