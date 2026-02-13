"""Tests for patch detection — raster to polygon conversion."""

import numpy as np
import pytest
from rasterio.transform import from_bounds

from app.services.patch_detector import extract_patches


def _make_test_data(patch_size=30, severity_val=3):
    """Create a simple severity raster with one clear patch."""
    h, w = 100, 100
    bbox = [-63.0, -10.5, -62.0, -10.0]
    transform = from_bounds(*bbox, w, h)

    severity = np.zeros((h, w), dtype=np.uint8)
    ndvi_diff = np.zeros((h, w), dtype=np.float32)

    # Create a square patch in the center
    r0, c0 = 35, 35
    severity[r0:r0 + patch_size, c0:c0 + patch_size] = severity_val
    ndvi_diff[r0:r0 + patch_size, c0:c0 + patch_size] = -0.55

    return severity, ndvi_diff, transform


class TestExtractPatches:
    def test_finds_patch(self):
        severity, ndvi_diff, transform = _make_test_data()
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        assert len(patches) >= 1

    def test_patch_has_correct_severity(self):
        severity, ndvi_diff, transform = _make_test_data(severity_val=3)
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        assert patches[0].severity == "HIGH"

    def test_patch_has_positive_area(self):
        severity, ndvi_diff, transform = _make_test_data()
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        assert patches[0].area_hectares > 0

    def test_patch_has_coordinates(self):
        severity, ndvi_diff, transform = _make_test_data()
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        assert len(patches[0].coordinates) > 0
        assert len(patches[0].coordinates[0]) > 3  # polygon ring

    def test_patch_has_confidence(self):
        severity, ndvi_diff, transform = _make_test_data()
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        assert 0 < patches[0].confidence <= 1.0

    def test_empty_raster_returns_no_patches(self):
        h, w = 100, 100
        severity = np.zeros((h, w), dtype=np.uint8)
        ndvi_diff = np.zeros((h, w), dtype=np.float32)
        transform = from_bounds(-63, -10.5, -62, -10, w, h)
        patches = extract_patches(severity, ndvi_diff, transform)
        assert len(patches) == 0

    def test_tiny_patch_filtered_out(self):
        """Patches smaller than sieve size should be removed."""
        severity, ndvi_diff, transform = _make_test_data(patch_size=2)
        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=10)
        assert len(patches) == 0

    def test_multiple_severity_levels(self):
        h, w = 100, 100
        bbox = [-63.0, -10.5, -62.0, -10.0]
        transform = from_bounds(*bbox, w, h)

        severity = np.zeros((h, w), dtype=np.uint8)
        ndvi_diff = np.full((h, w), -0.55, dtype=np.float32)

        # HIGH patch
        severity[10:30, 10:30] = 3
        # MEDIUM patch
        severity[50:70, 50:70] = 2
        # LOW patch
        severity[10:30, 70:90] = 1

        patches = extract_patches(severity, ndvi_diff, transform, min_size_pixels=4)
        severities = {p.severity for p in patches}
        assert "HIGH" in severities
        assert "MEDIUM" in severities
