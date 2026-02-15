from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import settings
from app.models import db
from app.models.schemas import (
    AlertResponse, InterventionRequest, InterventionResponse,
    PatchImpact, AggregateImpact,
)
from app.services.pipeline import get_ndvi_image
from app.services.firms import fetch_fire_hotspots
from app.services import carbon as carbon_svc
from app.services.storytelling import generate_narrative

router = APIRouter(tags=["alerts"])


@router.get("/api/alerts")
async def list_alerts():
    alerts = db.list_alerts()
    return [
        {
            "alert_id": a.alert_id,
            "timestamp": a.timestamp,
            "status": a.status,
            "patch_count": a.patch_count,
            "total_area_hectares": a.total_area_hectares,
            "region": a.region,
        }
        for a in alerts
    ]


@router.get("/api/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str):
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return alert


@router.get("/api/alerts/{alert_id}/geojson")
async def get_alert_geojson(alert_id: str):
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")

    features = []
    for patch in alert.patches:
        feat_props = {
            "id": patch.id,
            "severity": patch.severity,
            "area_hectares": patch.area_hectares,
            "confidence": patch.confidence,
            "ndvi_drop": patch.ndvi_drop,
            "centroid": patch.centroid,
        }
        if patch.impact:
            feat_props["impact"] = patch.impact.model_dump()
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": patch.coordinates,
            },
            "properties": feat_props,
        }
        features.append(feature)

    props = {
        "alert_id": alert.alert_id,
        "timestamp": alert.timestamp,
        "total_area_hectares": alert.total_area_hectares,
        "patch_count": alert.patch_count,
    }
    if alert.before_scene:
        props["before_scene"] = alert.before_scene.model_dump()
    if alert.after_scene:
        props["after_scene"] = alert.after_scene.model_dump()
    if alert.aggregate_impact:
        props["aggregate_impact"] = alert.aggregate_impact.model_dump()
    if alert.narrative:
        props["narrative"] = alert.narrative

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": props,
    }


@router.post("/api/alerts/{alert_id}/intervention", response_model=InterventionResponse)
async def run_intervention(alert_id: str, req: InterventionRequest):
    """Recompute impact estimates under a different intervention scenario."""
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    if not alert.patches:
        raise HTTPException(400, "No patches to evaluate")

    valid = {"natural_regeneration", "assisted_planting", "intensive_restoration"}
    if req.intervention not in valid:
        raise HTTPException(400, f"Invalid intervention. Choose from: {', '.join(valid)}")

    # Recompute impact for each patch under the new scenario
    updated_patches = []
    impacts = []
    natural_impacts = []
    for p in alert.patches:
        impact_dict = carbon_svc.estimate_patch_impact(
            p.area_hectares, p.severity, p.ndvi_drop, p.centroid[0],
            intervention=req.intervention,
        )
        new_patch = p.model_copy(update={"impact": PatchImpact(**impact_dict)})
        updated_patches.append(new_patch)
        impacts.append(impact_dict)

        # Also compute natural baseline for delta
        nat = carbon_svc.estimate_patch_impact(
            p.area_hectares, p.severity, p.ndvi_drop, p.centroid[0],
            intervention="natural_regeneration",
        )
        natural_impacts.append(nat)

    agg_dict = carbon_svc.aggregate_impact(impacts)
    agg = AggregateImpact(**agg_dict)

    nat_agg = carbon_svc.aggregate_impact(natural_impacts)

    # Compute deltas vs natural
    delta = None
    if req.intervention != "natural_regeneration":
        delta = {
            "regrowth_months_saved": nat_agg["avg_regrowth_months"] - agg.avg_regrowth_months,
            "regrowth_improvement_pct": round(
                (1 - agg.avg_regrowth_months / nat_agg["avg_regrowth_months"]) * 100
            ) if nat_agg["avg_regrowth_months"] > 0 else 0,
            "additional_cost_usd": agg.total_cost_estimate_usd - nat_agg["total_cost_estimate_usd"],
        }

    # Worst severity for narrative
    worst_sev = "HIGH" if any(p.severity == "HIGH" for p in alert.patches) else (
        "MEDIUM" if any(p.severity == "MEDIUM" for p in alert.patches) else "LOW"
    )

    interv_label = carbon_svc.INTERVENTION_MULTIPLIERS[req.intervention]["label"]

    # Best-case for narrative
    best_impacts = []
    for p in alert.patches:
        best = carbon_svc.estimate_patch_impact(
            p.area_hectares, p.severity, p.ndvi_drop, p.centroid[0],
            intervention="intensive_restoration",
        )
        best_impacts.append(best)
    best_agg = carbon_svc.aggregate_impact(best_impacts)

    narrative = generate_narrative(
        patch_count=len(alert.patches),
        total_area_hectares=alert.total_area_hectares,
        total_carbon_loss=agg.total_carbon_loss_tonnes,
        total_trees=agg.total_trees_to_replant,
        avg_regrowth_months=agg.avg_regrowth_months,
        intervention_label=interv_label,
        worst_severity=worst_sev,
        region_bbox=alert.region,
        best_case_regrowth=best_agg["avg_regrowth_months"] if req.intervention != "intensive_restoration" else None,
    )

    return InterventionResponse(
        alert_id=alert_id,
        intervention=req.intervention,
        intervention_label=interv_label,
        patches=updated_patches,
        aggregate_impact=agg,
        narrative=narrative,
        delta_vs_natural=delta,
    )


@router.get("/api/alerts/{alert_id}/before.png")
async def get_before_image(alert_id: str):
    data = get_ndvi_image(alert_id, "before")
    if not data:
        raise HTTPException(404, "Image not found")
    return Response(content=data, media_type="image/png")


@router.get("/api/alerts/{alert_id}/after.png")
async def get_after_image(alert_id: str):
    data = get_ndvi_image(alert_id, "after")
    if not data:
        raise HTTPException(404, "Image not found")
    return Response(content=data, media_type="image/png")


@router.get("/api/fires")
async def get_fire_hotspots(west: float, south: float, east: float, north: float, days: int = 5):
    """Get NASA FIRMS fire hotspots for a bounding box."""
    bbox = [west, south, east, north]
    points = fetch_fire_hotspots(bbox, days=days)
    return {
        "count": len(points),
        "points": points,
        "configured": bool(settings.nasa_firms_key),
    }
