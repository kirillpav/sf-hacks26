"""Convert severity raster to GeoJSON polygons with area and confidence metrics."""

from __future__ import annotations

import numpy as np
import rasterio.features
from rasterio.transform import Affine
from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union

from app.config import settings
from app.models.schemas import PatchInfo, Severity


# Approximate meters per degree at equator (good enough for area estimates)
_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LNG = 111_320  # adjusted per latitude in _polygon_area_hectares

# Simplify tolerance in degrees (~10m at equator) to reduce overlapping thin strips
_SIMPLIFY_TOLERANCE = 0.0001


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
    min_size_pixels: int = 12,
) -> list[PatchInfo]:
    """Extract deforestation patches from classified severity raster.

    Steps:
    1. Sieve small pixel groups to remove noise
    2. Vectorize to polygons per severity level
    3. Merge adjacent polygons to avoid overlapping thin strips
    4. Simplify geometries
    5. Filter by minimum hectares and return PatchInfo list
    """
    patches: list[PatchInfo] = []

    # Average NDVI drop per severity (for confidence)
    avg_drops = {}
    for sev_val in [1, 2, 3]:
        mask = severity_raster == sev_val
        if mask.any():
            avg_drops[sev_val] = float(np.nanmean(ndvi_diff[mask]))
        else:
            avg_drops[sev_val] = 0.0

    # Process each severity level separately
    for sev_val in [3, 2, 1]:  # HIGH first
        mask = (severity_raster == sev_val).astype(np.uint8)
        if mask.sum() == 0:
            continue

        # Sieve to remove tiny pixel clusters (larger = fewer noise polygons)
        sieved = rasterio.features.sieve(mask, size=min_size_pixels)

        # Vectorize
        shapes = list(rasterio.features.shapes(
            sieved, mask=sieved > 0, transform=transform
        ))

        geoms = []
        for geom_dict, value in shapes:
            geom = shape(geom_dict)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty or geom.area == 0:
                continue
            geoms.append(geom)

        if not geoms:
            continue

        # Merge adjacent polygons to reduce overlapping strips
        merged = unary_union(geoms)
        if merged.is_empty:
            continue

        # Decompose MultiPolygon or single Polygon into list
        if isinstance(merged, MultiPolygon):
            polys = [g for g in merged.geoms if isinstance(g, Polygon) and not g.is_empty]
        elif isinstance(merged, Polygon) and not merged.is_empty:
            polys = [merged]
        else:
            continue

        for geom in polys:
            if geom.is_empty or geom.area == 0:
                continue

            # Simplify to reduce jagged edges and overlapping artifacts
            geom = geom.simplify(_SIMPLIFY_TOLERANCE, preserve_topology=True)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty:
                continue
            if isinstance(geom, MultiPolygon):
                geom = max(geom.geoms, key=lambda g: g.area) if geom.geoms else None
                if geom is None:
                    continue

            centroid = geom.centroid
            area_ha = _polygon_area_hectares(geom, centroid.y)

            if area_ha < settings.min_patch_hectares:
                continue

            avg_drop = avg_drops.get(sev_val, 0.0)
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
