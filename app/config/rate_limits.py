"""Central rate-limit configuration."""

from __future__ import annotations

import os
from typing import Dict

RATE_LIMITS = {
    "binance": {"max_requests": 1200, "window": 60},
    "okx": {"max_requests": 20, "window": 1},
    "polygon": {"max_requests": 5, "window": 60},
}


def get_instance_count() -> int:
    """Return the configured instance count for local fallback throttling."""
    try:
        return max(1, int(os.getenv("INSTANCE_COUNT", "4")))
    except ValueError:
        return 4


def get_fallback_rate_limits() -> Dict[str, Dict[str, int]]:
    """Return conservative per-instance rate limits used during Redis fallback."""
    instance_count = get_instance_count()
    return {
        exchange: {
            "max_requests": max(1, config["max_requests"] // instance_count),
            "window": config["window"],
        }
        for exchange, config in RATE_LIMITS.items()
    }
