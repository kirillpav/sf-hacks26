#!/usr/bin/env python3
"""Generate synthetic GeoTIFF files for testing without real satellite data."""

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from app.demo.sample_data import generate_demo_ndvi


def main():
    data = generate_demo_ndvi()

    for name in ("before_ndvi", "after_ndvi"):
        path = f"sample_{name}.tif"
        arr = data[name]
        transform = data["transform"]

        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=arr.shape[0],
            width=arr.shape[1],
            count=1,
            dtype=arr.dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(arr, 1)

        print(f"Written: {path} ({arr.shape})")


if __name__ == "__main__":
    main()
