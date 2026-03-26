"""Tests for distributed rate limiter helpers."""

import asyncio

import pytest

from app.config.rate_limits import RATE_LIMITS
from app.services.rate_limiter import (
    acquire_rate_limit,
    acquire_rate_limit_sync,
    rate_limit,
    reset_local_rate_limiters,
)
from app.services.redis_client import reset_redis_state


@pytest.fixture(autouse=True)
def reset_rate_limit_state(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "false")
    monkeypatch.setenv("INSTANCE_COUNT", "1")
    reset_local_rate_limiters()
    asyncio.run(reset_redis_state())
    yield
    reset_local_rate_limiters()
    asyncio.run(reset_redis_state())


def test_acquire_rate_limit_sync_uses_local_fallback():
    """Sync acquisition should enforce fallback quotas."""
    RATE_LIMITS["test-exchange"] = {"max_requests": 2, "window": 60}
    try:
        assert acquire_rate_limit_sync("test-exchange", "client-1") is True
        assert acquire_rate_limit_sync("test-exchange", "client-1") is True
        assert acquire_rate_limit_sync("test-exchange", "client-1") is False
    finally:
        RATE_LIMITS.pop("test-exchange", None)


@pytest.mark.asyncio
async def test_acquire_rate_limit_async_uses_local_fallback():
    """Async acquisition should enforce fallback quotas."""
    RATE_LIMITS["test-exchange"] = {"max_requests": 1, "window": 60}
    try:
        assert await acquire_rate_limit("test-exchange", "client-2") is True
        assert await acquire_rate_limit("test-exchange", "client-2") is False
    finally:
        RATE_LIMITS.pop("test-exchange", None)


@pytest.mark.asyncio
async def test_rate_limit_decorator_resolves_identifier():
    """Decorator should apply separate limits per resolved identifier."""
    RATE_LIMITS["decorator-exchange"] = {"max_requests": 1, "window": 60}

    @rate_limit("decorator-exchange", identifier_key="symbol")
    async def limited(symbol: str) -> str:
        return symbol

    try:
        assert await limited("BTCUSDT") == "BTCUSDT"
        assert await limited("ETHUSDT") == "ETHUSDT"
        with pytest.raises(RuntimeError):
            await limited("BTCUSDT")
    finally:
        RATE_LIMITS.pop("decorator-exchange", None)
