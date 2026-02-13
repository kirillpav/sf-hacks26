"""Satellite Deforestation Alert System — FastAPI application."""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import health, analysis, alerts, regions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Deforestation Alert System",
    description="Detect deforestation from Sentinel-2 satellite imagery",
    version="0.1.0",
)

# Register routers
app.include_router(health.router)
app.include_router(analysis.router)
app.include_router(alerts.router)
app.include_router(regions.router)

# Serve frontend
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
