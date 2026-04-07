"""Scheduled task entrypoint for the daily digest pipeline."""

from __future__ import annotations

import logging
from typing import Any

from app.digest.config import load_daily_digest_config
from app.digest.generator import generate_daily_digest

logger = logging.getLogger(__name__)


async def send_daily_digest() -> dict[str, Any]:
    """Run the configured daily digest task when the feature is enabled.

    Returns:
        dict[str, Any]: A digest payload on success, or a small skipped payload
        when the feature is disabled.
    """

    config = load_daily_digest_config()
    if not config["enabled"]:
        logger.info("Skipping daily digest task because it is disabled")
        return {"status": "skipped", "reason": "disabled"}
    return await generate_daily_digest(config)
