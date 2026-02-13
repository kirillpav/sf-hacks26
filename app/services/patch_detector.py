"""Convert severity raster to GeoJSON polygons with area and confidence metrics."""

from __future__ import annotations

import numpy as np
import rasterio.features
from rasterio.transform import Affine
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from app.config import settings
from app.models.schemas import PatchInfo, Severity


# Approximate meters per degree at equator (good enough for area estimates)
_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LNG = 111_320  # adjusted per latitude in _polygon_area_hectares


def _polygon_area_hectares(geom, centroid_lat: float) -> float:
    """Estimate polygon area in hectares from WGS84 coordinates."""
    lng_scale = _M_PER_DEG_LNG * np.cos(np.radians(centroid_lat))
    lat_scale = _M_PER_DEG_LAT
    # Scale geometry to approximate meters
    coords = np.array(geom.exterior.coords)
    local_x = (coords[:, 0] - coords[:, 0].mean()) * lng_scale
    local_y = (coords[:, 1] - coords[:, 1].mean()) * lat_scale
    # Shoelace formula
    area_m2 = 0.5 * abs(
        np.sum(local_x[:-1] * local_y[1:] - local_x[1:] * local_y[:-1])
    )
    return area_m2 / 10_000  # m² to hectares


def _severity_label(val: int) -> Severity:
    return {1: Severity.LOW, 2: Severity.MEDIUM, 3: Severity.HIGH}.get(
        val, Severity.LOW
    )


def _compute_confidence(severity_val: int, ndvi_drop: float) -> float:
    """Heuristic confidence score based on severity and NDVI magnitude."""
    base = {1: 0.55, 2: 0.72, 3: 0.88}.get(severity_val, 0.5)
    # Boost confidence for larger drops
    boost = min(0.12, abs(ndvi_drop) * 0.1)
    return round(min(1.0, base + boost), 2)


def extract_patches(
    severity_raster: np.ndarray,
    ndvi_diff: np.ndarray,
    transform: Affine,
    min_size_pixels: int = 6,
) -> list[PatchInfo]:
    """Extract deforestation patches from classified severity raster.

    Steps:
    1. Sieve small pixel groups to remove noise
    2. Vectorize to polygons per severity level
    3. Compute area, filter by minimum hectares
    4. Return PatchInfo list
    """
    patches: list[PatchInfo] = []

    # Process each severity level separately
    for sev_val in [3, 2, 1]:  # HIGH first
        mask = (severity_raster == sev_val).astype(np.uint8)
        if mask.sum() == 0:
            continue

        # Sieve to remove tiny pixel clusters
        sieved = rasterio.features.sieve(mask, size=min_size_pixels)

        # Vectorize
        shapes = list(rasterio.features.shapes(
            sieved, mask=sieved > 0, transform=transform
        ))

        for geom_dict, value in shapes:
            geom = shape(geom_dict)
            if not geom.is_valid:
                geom = geom.buffer(0)

            centroid = geom.centroid
            area_ha = _polygon_area_hectares(geom, centroid.y)

            if area_ha < settings.min_patch_hectares:
                continue

            # Average NDVI drop within this polygon's bounding box (approximate)
            minx, miny, maxx, maxy = geom.bounds
            avg_drop = float(np.nanmean(
                ndvi_diff[severity_raster == sev_val]
            ))

            confidence = _compute_confidence(sev_val, avg_drop)

            coords = [list(mapping(geom)["coordinates"][0])]

            patches.append(PatchInfo(
                coordinates=coords,
                centroid=[round(centroid.y, 6), round(centroid.x, 6)],
                area_hectares=round(area_ha, 2),
                confidence=confidence,
                severity=_severity_label(sev_val),
                ndvi_drop=round(avg_drop, 3),
            ))

    return patches
