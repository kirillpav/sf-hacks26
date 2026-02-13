from fastapi import APIRouter, HTTPException

from app.models import db
from app.models.schemas import RegionCreate, RegionResponse

router = APIRouter(tags=["regions"])


@router.post("/api/regions", response_model=RegionResponse, status_code=201)
async def create_region(region: RegionCreate):
    west, south, east, north = region.bbox
    if west >= east or south >= north:
        raise HTTPException(400, "Invalid bbox")
    return db.create_region(region.name, region.bbox, region.description)


@router.get("/api/regions")
async def list_regions():
    return db.list_regions()
