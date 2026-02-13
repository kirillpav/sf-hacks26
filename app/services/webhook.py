"""Async webhook dispatch."""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def fire_webhook(payload: dict, url: str | None = None) -> bool:
    """POST JSON payload to webhook URL. Returns True on success."""
    target = url or settings.webhook_url
    if not target:
        logger.info("No webhook URL configured, skipping")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(target, json=payload)
            resp.raise_for_status()
            logger.info("Webhook delivered to %s (status %d)", target, resp.status_code)
            return True
    except Exception as e:
        logger.warning("Webhook delivery failed: %s", e)
        return False
