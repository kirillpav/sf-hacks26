"""NDVI computation, differencing, and deforestation classification."""

from __future__ import annotations

import numpy as np

from app.config import settings


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute NDVI from red (B04) and NIR (B08) bands.

    NDVI = (NIR - Red) / (NIR + Red)
    Returns float32 array with values in [-1, 1]. NoData where both bands are 0.
    """
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)

    denominator = nir + red
    # Avoid division by zero
    valid = denominator > 0
    ndvi = np.where(valid, (nir - red) / denominator, np.nan)
    return ndvi.astype(np.float32)


def compute_ndvi_diff(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Compute NDVI change: after - before.

    Negative values indicate vegetation loss.
    """
    return (after - before).astype(np.float32)


def classify_deforestation(ndvi_diff: np.ndarray) -> np.ndarray:
    """Classify NDVI drop into severity levels.

    Returns uint8 raster:
        0 = no significant change
        1 = LOW severity (drop > threshold_low)
        2 = MEDIUM severity (drop > threshold_medium)
        3 = HIGH severity (drop > threshold_high)
    """
    # ndvi_diff is negative where vegetation was lost
    drop = -ndvi_diff  # make positive for easier comparison

    severity = np.zeros(ndvi_diff.shape, dtype=np.uint8)
    severity[drop > settings.ndvi_threshold_low] = 1
    severity[drop > settings.ndvi_threshold_medium] = 2
    severity[drop > settings.ndvi_threshold_high] = 3

    return severity
