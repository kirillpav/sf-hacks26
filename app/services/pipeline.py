"""Orchestrates the full deforestation analysis pipeline."""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from app.config import settings
from app.models import db
from app.models.schemas import AnalysisRequest, AnalysisStatus, PatchInfo
from app.services import ndvi as ndvi_svc
from app.services import patch_detector
from app.services import webhook
from app.services.geocoder import region_to_bbox

logger = logging.getLogger(__name__)

# Store NDVI images in memory for serving
_ndvi_images: dict[str, dict[str, bytes]] = {}


def get_ndvi_image(alert_id: str, which: str) -> bytes | None:
    """Get stored before/after NDVI PNG image."""
    return _ndvi_images.get(alert_id, {}).get(which)


def _render_ndvi_png(ndvi_array: np.ndarray, title: str = "") -> bytes:
    """Render NDVI array to PNG bytes with a green-brown colormap."""
    fig, ax = plt.subplots(1, 1, figsize=(6, 6))

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ndvi",
        [(0.6, 0.3, 0.1), (0.9, 0.9, 0.3), (0.1, 0.6, 0.1), (0.0, 0.3, 0.0)],
    )

    im = ax.imshow(ndvi_array, cmap=cmap, vmin=0, vmax=1)
    ax.set_title(title, fontsize=12)
    ax.axis("off")
    fig.colorbar(im, ax=ax, shrink=0.8, label="NDVI")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def run_analysis(alert_id: str, request: AnalysisRequest) -> None:
    """Run the full analysis pipeline (called as background task)."""
    try:
        # Resolve bbox
        bbox = request.bbox
        if not bbox and request.region_name:
            db.update_alert(alert_id, status=AnalysisStatus.RUNNING, progress=5)
            bbox = region_to_bbox(request.region_name)
            if not bbox:
                db.update_alert(
                    alert_id,
                    status=AnalysisStatus.FAILED,
                    error=f"Could not geocode region: {request.region_name}",
                )
                return

        if not bbox:
            db.update_alert(
                alert_id,
                status=AnalysisStatus.FAILED,
                error="No bbox or region_name provided",
            )
            return

        # Validate bbox size
        width = abs(bbox[2] - bbox[0])
        height = abs(bbox[3] - bbox[1])
        if width > settings.max_bbox_degrees or height > settings.max_bbox_degrees:
            db.update_alert(
                alert_id,
                status=AnalysisStatus.FAILED,
                error=f"Bbox too large (max {settings.max_bbox_degrees}° per side)",
            )
            return

        db.update_alert(
            alert_id,
            status=AnalysisStatus.RUNNING,
            region=bbox,
            progress=10,
        )

        # Fetch NDVI data (demo or real)
        if settings.demo_mode:
            before_ndvi, after_ndvi, transform, crs_str = await _fetch_demo_data(
                alert_id, bbox
            )
        else:
            before_ndvi, after_ndvi, transform, crs_str = await _fetch_real_data(
                alert_id, bbox, request
            )

        db.update_alert(alert_id, progress=60)

        # Compute NDVI diff and classify
        ndvi_diff = ndvi_svc.compute_ndvi_diff(before_ndvi, after_ndvi)
        severity = ndvi_svc.classify_deforestation(ndvi_diff)

        db.update_alert(alert_id, progress=75)

        # Extract patches
        patches = patch_detector.extract_patches(severity, ndvi_diff, transform)

        db.update_alert(alert_id, progress=85)

        # Generate NDVI visualizations
        before_png = _render_ndvi_png(before_ndvi, "NDVI Before")
        after_png = _render_ndvi_png(after_ndvi, "NDVI After")
        _ndvi_images[alert_id] = {"before": before_png, "after": after_png}

        db.update_alert(alert_id, progress=90)

        # Calculate totals
        total_area = round(sum(p.area_hectares for p in patches), 2)

        db.update_alert(
            alert_id,
            status=AnalysisStatus.COMPLETED,
            progress=100,
            patches=patches,
            total_area_hectares=total_area,
            patch_count=len(patches),
        )

        # Fire webhook
        webhook_url = request.webhook_url or settings.webhook_url
        if webhook_url:
            payload = {
                "alert_id": alert_id,
                "timestamp": db.get_alert(alert_id).timestamp,
                "region": bbox,
                "patches": [p.model_dump() for p in patches],
                "total_area_hectares": total_area,
                "patch_count": len(patches),
            }
            await webhook.fire_webhook(payload, webhook_url)

        logger.info(
            "Analysis %s completed: %d patches, %.1f ha total",
            alert_id, len(patches), total_area,
        )

    except Exception as e:
        logger.exception("Analysis %s failed", alert_id)
        db.update_alert(
            alert_id,
            status=AnalysisStatus.FAILED,
            error=str(e),
        )


async def _fetch_demo_data(alert_id: str, bbox: list[float]):
    """Generate synthetic NDVI data for demo mode."""
    from app.demo.sample_data import generate_demo_ndvi

    db.update_alert(alert_id, progress=20)
    # Simulate processing time
    await asyncio.sleep(1)

    data = generate_demo_ndvi(bbox)
    db.update_alert(alert_id, progress=50)

    return (
        data["before_ndvi"],
        data["after_ndvi"],
        data["transform"],
        data["crs"],
    )


async def _fetch_real_data(alert_id: str, bbox: list[float], request: AnalysisRequest):
    """Fetch real Sentinel-2 data and compute NDVI."""
    from app.services.imagery import search_scenes, fetch_band_pair

    # Default date ranges if not provided
    now = datetime.utcnow()
    before_start = request.before_start or (now - timedelta(days=365)).strftime("%Y-%m-%d")
    before_end = request.before_end or (now - timedelta(days=180)).strftime("%Y-%m-%d")
    after_start = request.after_start or (now - timedelta(days=90)).strftime("%Y-%m-%d")
    after_end = request.after_end or now.strftime("%Y-%m-%d")

    db.update_alert(alert_id, progress=15)

    # Search for before scenes
    before_scenes = search_scenes(bbox, before_start, before_end)
    if not before_scenes:
        raise ValueError(f"No scenes found for 'before' period ({before_start} to {before_end})")

    db.update_alert(alert_id, progress=25)

    # Search for after scenes
    after_scenes = search_scenes(bbox, after_start, after_end)
    if not after_scenes:
        raise ValueError(f"No scenes found for 'after' period ({after_start} to {after_end})")

    db.update_alert(alert_id, progress=35)

    # Fetch band pairs (use least cloudy scene)
    before_red, before_nir, meta = fetch_band_pair(before_scenes[0], bbox)
    db.update_alert(alert_id, progress=45)

    after_red, after_nir, _ = fetch_band_pair(after_scenes[0], bbox)
    db.update_alert(alert_id, progress=55)

    # Ensure same shape
    min_h = min(before_red.shape[0], after_red.shape[0])
    min_w = min(before_red.shape[1], after_red.shape[1])

    before_ndvi = ndvi_svc.compute_ndvi(
        before_red[:min_h, :min_w], before_nir[:min_h, :min_w]
    )
    after_ndvi = ndvi_svc.compute_ndvi(
        after_red[:min_h, :min_w], after_nir[:min_h, :min_w]
    )

    return before_ndvi, after_ndvi, meta["transform"], meta["crs"]
