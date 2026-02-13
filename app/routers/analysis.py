from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models import db
from app.models.schemas import AnalysisAccepted, AnalysisRequest, AlertResponse
from app.services.pipeline import run_analysis

router = APIRouter(tags=["analysis"])


@router.post("/api/analyze", response_model=AnalysisAccepted, status_code=202)
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
):
    if not request.bbox and not request.region_name:
        raise HTTPException(400, "Provide either bbox or region_name")

    # Validate bbox format
    if request.bbox:
        west, south, east, north = request.bbox
        if west >= east or south >= north:
            raise HTTPException(400, "Invalid bbox: west < east and south < north required")

    # Create alert record
    bbox = request.bbox or [0, 0, 0, 0]
    alert = db.create_alert(bbox)

    # Run pipeline in background
    background_tasks.add_task(run_analysis, alert.alert_id, request)

    return AnalysisAccepted(
        analysis_id=alert.alert_id,
        message="Analysis started" + (" (demo mode)" if __import__("app.config", fromlist=["settings"]).settings.demo_mode else ""),
    )


@router.get("/api/analyze/{analysis_id}/status")
async def get_status(analysis_id: str):
    alert = db.get_alert(analysis_id)
    if not alert:
        raise HTTPException(404, "Analysis not found")
    return {
        "analysis_id": analysis_id,
        "status": alert.status,
        "progress": alert.progress,
        "error": alert.error,
    }
