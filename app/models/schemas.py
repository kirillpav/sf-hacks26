from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnalysisRequest(BaseModel):
    bbox: Optional[list[float]] = Field(
        None,
        description="Bounding box [west, south, east, north] in WGS84",
        min_length=4,
        max_length=4,
    )
    region_name: Optional[str] = Field(
        None, description="Region name to geocode (alternative to bbox)"
    )
    before_start: Optional[str] = Field(
        None, description="Start of 'before' period (YYYY-MM-DD)"
    )
    before_end: Optional[str] = Field(
        None, description="End of 'before' period (YYYY-MM-DD)"
    )
    after_start: Optional[str] = Field(
        None, description="Start of 'after' period (YYYY-MM-DD)"
    )
    after_end: Optional[str] = Field(
        None, description="End of 'after' period (YYYY-MM-DD)"
    )
    webhook_url: Optional[str] = Field(
        None, description="Override webhook URL for this analysis"
    )


class AnalysisStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PatchImpact(BaseModel):
    """Per-patch carbon/restoration estimates."""
    biome: str = ""
    carbon_loss_tonnes: float = 0.0
    trees_to_replant: int = 0
    regrowth_months: int = 0
    intervention: str = "natural_regeneration"
    intervention_label: str = "Natural Regeneration"
    cost_estimate_usd: int = 0


class PatchInfo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    coordinates: list[list[list[float]]] = Field(
        description="Polygon coordinates [[[lng, lat], ...]]"
    )
    centroid: list[float] = Field(description="[lat, lng] of centroid")
    area_hectares: float
    confidence: float = Field(ge=0, le=1)
    severity: Severity
    ndvi_drop: float
    impact: Optional[PatchImpact] = None


class SceneInfo(BaseModel):
    """Sentinel-2 scene metadata (LIVE mode only)."""
    scene_id: str
    acquisition_date: str


class AggregateImpact(BaseModel):
    """Alert-level rollup of carbon/restoration estimates."""
    total_carbon_loss_tonnes: float = 0.0
    total_trees_to_replant: int = 0
    avg_regrowth_months: int = 0
    total_cost_estimate_usd: int = 0


class AlertResponse(BaseModel):
    alert_id: str
    timestamp: str
    region: list[float]
    status: AnalysisStatus
    progress: int = Field(ge=0, le=100)
    patches: list[PatchInfo] = []
    total_area_hectares: float = 0.0
    patch_count: int = 0
    error: Optional[str] = None
    before_scene: Optional[SceneInfo] = None
    after_scene: Optional[SceneInfo] = None
    aggregate_impact: Optional[AggregateImpact] = None
    narrative: Optional[str] = None


class AnalysisAccepted(BaseModel):
    analysis_id: str
    status: str = "ACCEPTED"
    message: str = "Analysis started"


class RegionCreate(BaseModel):
    name: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    description: Optional[str] = None


class RegionResponse(BaseModel):
    id: str
    name: str
    bbox: list[float]
    description: Optional[str] = None
    created_at: str


class InterventionRequest(BaseModel):
    intervention: str = Field(
        description="One of: natural_regeneration, assisted_planting, intensive_restoration"
    )


class InterventionResponse(BaseModel):
    alert_id: str
    intervention: str
    intervention_label: str
    patches: list[PatchInfo]
    aggregate_impact: AggregateImpact
    narrative: str
    delta_vs_natural: Optional[dict] = Field(
        None, description="Improvement vs natural_regeneration baseline"
    )


class WebhookPayload(BaseModel):
    alert_id: str
    timestamp: str
    region: list[float]
    patches: list[dict]
    total_area_hectares: float
    patch_count: int
    aggregate_impact: Optional[dict] = None
    narrative: Optional[str] = None
