from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    demo_mode: bool = True
    webhook_url: str = ""
    nasa_firms_key: str = ""

    # NDVI change thresholds (magnitude of drop)
    ndvi_threshold_low: float = 0.3
    ndvi_threshold_medium: float = 0.4
    ndvi_threshold_high: float = 0.5

    # Minimum patch size to report
    min_patch_hectares: float = 1.0

    # Max bounding box size in degrees (~1° ≈ 111 km)
    max_bbox_degrees: float = 1.0

    # STAC catalog
    stac_catalog_url: str = "https://earth-search.aws.element84.com/v1"
    stac_collection: str = "sentinel-2-l2a"

    # Overview level for COG reads (higher = faster but coarser)
    cog_overview_level: int = 2

    # Max cloud cover percentage for scene search
    max_cloud_cover: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
