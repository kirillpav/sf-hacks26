"""Tests for NDVI computation and classification."""

import numpy as np
import pytest

from app.services.ndvi import compute_ndvi, compute_ndvi_diff, classify_deforestation


class TestComputeNDVI:
    def test_healthy_vegetation(self):
        """NIR >> Red → high positive NDVI."""
        red = np.array([[100, 200]], dtype=np.float32)
        nir = np.array([[800, 600]], dtype=np.float32)
        ndvi = compute_ndvi(red, nir)
        assert ndvi[0, 0] == pytest.approx(0.7777, abs=0.01)
        assert ndvi[0, 1] == pytest.approx(0.5, abs=0.01)

    def test_bare_soil(self):
        """NIR ≈ Red → NDVI near 0."""
        red = np.array([[500]], dtype=np.float32)
        nir = np.array([[520]], dtype=np.float32)
        ndvi = compute_ndvi(red, nir)
        assert abs(ndvi[0, 0]) < 0.05

    def test_water(self):
        """Red > NIR → negative NDVI."""
        red = np.array([[300]], dtype=np.float32)
        nir = np.array([[100]], dtype=np.float32)
        ndvi = compute_ndvi(red, nir)
        assert ndvi[0, 0] < 0

    def test_zero_bands(self):
        """Both bands zero → NaN."""
        red = np.array([[0]], dtype=np.float32)
        nir = np.array([[0]], dtype=np.float32)
        ndvi = compute_ndvi(red, nir)
        assert np.isnan(ndvi[0, 0])

    def test_output_dtype(self):
        red = np.array([[100]], dtype=np.float32)
        nir = np.array([[800]], dtype=np.float32)
        ndvi = compute_ndvi(red, nir)
        assert ndvi.dtype == np.float32


class TestNDVIDiff:
    def test_vegetation_loss(self):
        """After < before → negative diff."""
        before = np.array([[0.8, 0.7]], dtype=np.float32)
        after = np.array([[0.3, 0.2]], dtype=np.float32)
        diff = compute_ndvi_diff(before, after)
        assert diff[0, 0] == pytest.approx(-0.5, abs=0.01)
        assert diff[0, 1] == pytest.approx(-0.5, abs=0.01)

    def test_no_change(self):
        before = np.array([[0.6]], dtype=np.float32)
        after = np.array([[0.6]], dtype=np.float32)
        diff = compute_ndvi_diff(before, after)
        assert diff[0, 0] == pytest.approx(0.0, abs=0.001)

    def test_vegetation_gain(self):
        before = np.array([[0.3]], dtype=np.float32)
        after = np.array([[0.7]], dtype=np.float32)
        diff = compute_ndvi_diff(before, after)
        assert diff[0, 0] > 0


class TestClassifyDeforestation:
    def test_no_change(self):
        diff = np.array([[0.0, -0.1, -0.2]], dtype=np.float32)
        severity = classify_deforestation(diff)
        assert severity[0, 0] == 0
        assert severity[0, 1] == 0
        assert severity[0, 2] == 0

    def test_low_severity(self):
        diff = np.array([[-0.35]], dtype=np.float32)
        severity = classify_deforestation(diff)
        assert severity[0, 0] == 1

    def test_medium_severity(self):
        diff = np.array([[-0.45]], dtype=np.float32)
        severity = classify_deforestation(diff)
        assert severity[0, 0] == 2

    def test_high_severity(self):
        diff = np.array([[-0.55]], dtype=np.float32)
        severity = classify_deforestation(diff)
        assert severity[0, 0] == 3

    def test_output_dtype(self):
        diff = np.array([[-0.5]], dtype=np.float32)
        severity = classify_deforestation(diff)
        assert severity.dtype == np.uint8
