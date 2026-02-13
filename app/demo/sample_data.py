"""Generate synthetic NDVI data simulating a Rondonia deforestation scene.

Uses fixed random seed for reproducible demo results.
Generates 'before' NDVI (healthy forest) and 'after' NDVI (with deforestation patches).
"""

from __future__ import annotations

import numpy as np
from rasterio.transform import from_bounds


# Rondonia, Brazil — a well-known deforestation hotspot
DEMO_BBOX = [-63.0, -10.5, -62.0, -10.0]  # [west, south, east, north]

# Grid size for synthetic rasters
GRID_H = 256
GRID_W = 256


def _make_forest_ndvi(rng: np.random.Generator, shape: tuple[int, int]) -> np.ndarray:
    """Create a realistic-looking forest NDVI layer (values 0.6-0.9)."""
    base = 0.75 + 0.05 * rng.standard_normal(shape)
    # Add some smooth spatial variation
    y, x = np.mgrid[0:shape[0], 0:shape[1]]
    wave = 0.03 * np.sin(x / 20.0) * np.cos(y / 25.0)
    ndvi = np.clip(base + wave, 0.4, 0.95).astype(np.float32)
    return ndvi


def _add_deforestation_patches(
    ndvi: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Burn 3-4 deforestation patches into the NDVI array."""
    result = ndvi.copy()
    patches = [
        # (row, col, radius, severity) — simulating different clearing patterns
        (80, 100, 25, 0.55),   # Large high-severity clearing
        (160, 180, 18, 0.45),  # Medium clearing
        (50, 200, 12, 0.35),   # Smaller moderate clearing
        (200, 60, 15, 0.50),   # Medium-large clearing
    ]
    for row, col, radius, drop in patches:
        yy, xx = np.ogrid[0:ndvi.shape[0], 0:ndvi.shape[1]]
        mask = ((yy - row) ** 2 + (xx - col) ** 2) <= radius ** 2
        # Add some noise to the patch edges
        edge_noise = 0.05 * rng.standard_normal(ndvi.shape)
        result[mask] = result[mask] - drop + edge_noise[mask]

    return np.clip(result, 0.05, 0.95).astype(np.float32)


def generate_demo_ndvi(
    bbox: list[float] | None = None,
) -> dict:
    """Generate synthetic before/after NDVI arrays with transform metadata.

    Returns dict with keys:
        before_ndvi, after_ndvi: np.ndarray (float32, shape HxW)
        transform: rasterio Affine transform
        crs: str
        bbox: list[float]
        shape: tuple[int, int]
    """
    bbox = bbox or DEMO_BBOX
    rng = np.random.default_rng(seed=42)

    before_ndvi = _make_forest_ndvi(rng, (GRID_H, GRID_W))
    after_ndvi = _add_deforestation_patches(before_ndvi, rng)

    west, south, east, north = bbox
    transform = from_bounds(west, south, east, north, GRID_W, GRID_H)

    return {
        "before_ndvi": before_ndvi,
        "after_ndvi": after_ndvi,
        "transform": transform,
        "crs": "EPSG:4326",
        "bbox": bbox,
        "shape": (GRID_H, GRID_W),
    }
