"""Tests for worker smoke tasks."""

from unittest.mock import AsyncMock

import pytest

from app.tasks.smoke import worker_healthcheck


@pytest.mark.asyncio
async def test_worker_healthcheck_writes_marker():
    """Smoke task should write a marker and timestamp into Redis."""
    redis = AsyncMock()
    result = await worker_healthcheck({"redis": redis}, marker="healthy")

    assert result["marker"] == "healthy"
    assert "timestamp" in result
    assert redis.set.await_count == 2
