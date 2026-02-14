"""NASA FIRMS active fire data fetching."""

from __future__ import annotations

import csv
import io
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# NASA FIRMS Area API: /api/area/csv/{KEY}/{SOURCE}/{bbox}/1
# bbox format: west,south,east,north
# Returns CSV with columns: latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, etc.
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SOURCE = "VIIRS_SNPP_NRT"


def fetch_fire_hotspots(bbox: list[float], days: int = 5) -> list[dict]:
    """Fetch active fire detections from NASA FIRMS for a bounding box.

    Args:
        bbox: [west, south, east, north] in WGS84
        days: number of days to query (1-5)

    Returns:
        List of dicts with lat, lon, acq_date, brightness, etc.
    """
    if not settings.nasa_firms_key:
        logger.info("NASA FIRMS key not configured")
        return []

    days = max(1, min(5, days))
    west, south, east, north = bbox
    coords = f"{west},{south},{east},{north}"
    url = f"{FIRMS_BASE}/{settings.nasa_firms_key}/{SOURCE}/{coords}/{days}"

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning("FIRMS fetch failed: %s", e)
        return []

    rows = []
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        try:
            lat = float(row.get("latitude", 0))
            lon = float(row.get("longitude", 0))
            rows.append({
                "lat": lat,
                "lon": lon,
                "acq_date": row.get("acq_date", ""),
                "brightness": row.get("bright_ti4", ""),
            })
        except (ValueError, KeyError):
            continue
    return rows
