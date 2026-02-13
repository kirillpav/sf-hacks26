"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "demo_mode" in data

    def test_health_has_version(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert "version" in data


class TestAnalysisEndpoint:
    def test_analyze_requires_bbox_or_region(self):
        resp = client.post("/api/analyze", json={})
        assert resp.status_code == 400

    def test_analyze_accepts_bbox(self):
        resp = client.post("/api/analyze", json={
            "bbox": [-63.0, -10.5, -62.0, -10.0]
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "analysis_id" in data

    def test_analyze_accepts_region_name(self):
        resp = client.post("/api/analyze", json={
            "region_name": "Rondonia"
        })
        assert resp.status_code == 202

    def test_analyze_invalid_bbox(self):
        resp = client.post("/api/analyze", json={
            "bbox": [-62.0, -10.0, -63.0, -10.5]  # west > east
        })
        assert resp.status_code == 400

    def test_status_not_found(self):
        resp = client.get("/api/analyze/nonexistent/status")
        assert resp.status_code == 404


class TestAlertsEndpoint:
    def test_list_alerts(self):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_alert_not_found(self):
        resp = client.get("/api/alerts/nonexistent")
        assert resp.status_code == 404

    def test_geojson_not_found(self):
        resp = client.get("/api/alerts/nonexistent/geojson")
        assert resp.status_code == 404


class TestRegionsEndpoint:
    def test_create_and_list_regions(self):
        resp = client.post("/api/regions", json={
            "name": "Test Region",
            "bbox": [-63.0, -10.5, -62.0, -10.0],
            "description": "A test region"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Region"
        assert "id" in data

        # List should include it
        resp = client.get("/api/regions")
        assert resp.status_code == 200
        regions = resp.json()
        assert any(r["name"] == "Test Region" for r in regions)

    def test_create_region_invalid_bbox(self):
        resp = client.post("/api/regions", json={
            "name": "Bad",
            "bbox": [-62.0, -10.0, -63.0, -10.5]
        })
        assert resp.status_code == 400
