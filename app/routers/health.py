from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "version": "0.1.0",
    }
