"""Sentinel-2 imagery search and COG band fetching via Earth Search STAC."""

from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import rasterio
from pystac_client import Client

from app.config import settings

# Allow unsigned access to AWS open data
os.environ["AWS_NO_SIGN_REQUEST"] = "YES"


def search_scenes(
    bbox: list[float],
    date_start: str,
    date_end: str,
    max_cloud: int | None = None,
) -> list[dict]:
    """Search Earth Search STAC for Sentinel-2 L2A scenes.

    Returns list of scene dicts with asset URLs.
    """
    catalog = Client.open(settings.stac_catalog_url)
    max_cloud = max_cloud or settings.max_cloud_cover

    search = catalog.search(
        collections=[settings.stac_collection],
        bbox=bbox,
        datetime=f"{date_start}/{date_end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
        max_items=10,
        sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    )

    items = list(search.items())
    scenes = []
    for item in items:
        scenes.append({
            "id": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else "",
            "cloud_cover": item.properties.get("eo:cloud_cover", 0),
            "bbox": list(item.bbox) if item.bbox else bbox,
            "assets": {
                "red": item.assets.get("red", item.assets.get("B04", None)),
                "nir": item.assets.get("nir", item.assets.get("B08", None)),
            },
        })

    return scenes


def fetch_band(
    asset,
    bbox: list[float],
    overview_level: int | None = None,
) -> tuple[np.ndarray, dict]:
    """Read a single band from a COG asset, windowed to bbox.

    The bbox is expected in EPSG:4326 (lon/lat).  Sentinel-2 COGs are stored
    in UTM, so we reproject the bbox to the dataset's native CRS before
    computing the read window.

    Returns (band_array, metadata_dict) where metadata includes transform and crs.
    """
    from pyproj import Transformer
    from rasterio.windows import from_bounds
    from rasterio.transform import from_bounds as tfm_from_bounds

    href = asset.href if hasattr(asset, "href") else str(asset)
    overview_level = overview_level or settings.cog_overview_level

    with rasterio.open(href) as src:
        # Reproject bbox from EPSG:4326 to the dataset CRS (usually UTM)
        dst_crs = str(src.crs)
        if dst_crs.upper() != "EPSG:4326":
            transformer = Transformer.from_crs(
                "EPSG:4326", dst_crs, always_xy=True
            )
            xs, ys = transformer.transform(
                [bbox[0], bbox[2]], [bbox[1], bbox[3]]
            )
            native_bbox = [min(xs), min(ys), max(xs), max(ys)]
        else:
            native_bbox = bbox

        window = from_bounds(*native_bbox, transform=src.transform)

        # Clamp window to the raster extent
        window = window.intersection(
            rasterio.windows.Window(0, 0, src.width, src.height)
        )

        # Read at overview level for speed
        if src.overviews(1) and overview_level > 0:
            ovr_factors = src.overviews(1)
            if overview_level <= len(ovr_factors):
                factor = ovr_factors[overview_level - 1]
            else:
                factor = ovr_factors[-1] if ovr_factors else 1
        else:
            factor = 1

        out_shape = (
            max(1, int(window.height / factor)),
            max(1, int(window.width / factor)),
        )

        data = src.read(
            1,
            window=window,
            out_shape=out_shape,
            resampling=rasterio.enums.Resampling.nearest,
        )

        out_transform = tfm_from_bounds(
            *bbox, out_shape[1], out_shape[0]
        )

        meta = {
            "transform": out_transform,
            "crs": dst_crs,
            "shape": out_shape,
        }

    return data.astype(np.float32), meta


def fetch_band_pair(
    scene: dict,
    bbox: list[float],
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Fetch red (B04) and NIR (B08) bands for a scene.

    Returns (red_array, nir_array, metadata).
    """
    red_asset = scene["assets"]["red"]
    nir_asset = scene["assets"]["nir"]

    red, meta = fetch_band(red_asset, bbox)
    nir, _ = fetch_band(nir_asset, bbox)

    # Ensure same shape
    min_h = min(red.shape[0], nir.shape[0])
    min_w = min(red.shape[1], nir.shape[1])
    red = red[:min_h, :min_w]
    nir = nir[:min_h, :min_w]

    return red, nir, meta
