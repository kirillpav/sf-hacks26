"""In-memory data store for MVP — no database needed."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.models.schemas import (
    AlertResponse,
    AnalysisStatus,
    RegionResponse,
)

# Stores keyed by ID
_alerts: dict[str, AlertResponse] = {}
_regions: dict[str, RegionResponse] = {}


# --------------- Alerts ---------------

def create_alert(bbox: list[float]) -> AlertResponse:
    alert_id = str(uuid.uuid4())
    alert = AlertResponse(
        alert_id=alert_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        region=bbox,
        status=AnalysisStatus.PENDING,
        progress=0,
    )
    _alerts[alert_id] = alert
    return alert


def get_alert(alert_id: str) -> Optional[AlertResponse]:
    return _alerts.get(alert_id)


def update_alert(alert_id: str, **kwargs) -> Optional[AlertResponse]:
    alert = _alerts.get(alert_id)
    if not alert:
        return None
    updated = alert.model_copy(update=kwargs)
    _alerts[alert_id] = updated
    return updated


def list_alerts() -> list[AlertResponse]:
    return list(_alerts.values())


# --------------- Regions ---------------

def create_region(name: str, bbox: list[float], description: Optional[str] = None) -> RegionResponse:
    region_id = str(uuid.uuid4())[:8]
    region = RegionResponse(
        id=region_id,
        name=name,
        bbox=bbox,
        description=description,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _regions[region_id] = region
    return region


def get_region(region_id: str) -> Optional[RegionResponse]:
    return _regions.get(region_id)


def list_regions() -> list[RegionResponse]:
    return list(_regions.values())
