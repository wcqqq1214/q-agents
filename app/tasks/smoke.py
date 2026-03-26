"""Lightweight tasks for worker health and integration smoke tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


async def worker_healthcheck(
    ctx: Dict[str, Any],
    marker: str = "ok",
) -> Dict[str, str]:
    """Persist a simple marker in Redis so worker consumption can be verified."""
    redis = ctx["redis"]
    timestamp = datetime.now(timezone.utc).isoformat()
    await redis.set("worker:healthcheck:last", marker.encode("utf-8"), ex=300)
    await redis.set("worker:healthcheck:ts", timestamp.encode("utf-8"), ex=300)
    return {"marker": marker, "timestamp": timestamp}
