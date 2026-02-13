from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import db
from app.models.schemas import AlertResponse
from app.services.pipeline import get_ndvi_image

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
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": patch.coordinates,
            },
            "properties": {
                "id": patch.id,
                "severity": patch.severity,
                "area_hectares": patch.area_hectares,
                "confidence": patch.confidence,
                "ndvi_drop": patch.ndvi_drop,
                "centroid": patch.centroid,
            },
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "alert_id": alert.alert_id,
            "timestamp": alert.timestamp,
            "total_area_hectares": alert.total_area_hectares,
            "patch_count": alert.patch_count,
        },
    }


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
