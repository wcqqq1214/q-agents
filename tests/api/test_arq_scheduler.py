"""Tests for ARQ-backed scheduling helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from app.api.main import close_arq_pool, create_arq_pool, enqueue_daily_ohlc_job


@pytest.mark.asyncio
async def test_create_arq_pool_skips_when_redis_disabled(monkeypatch):
    """ARQ pool creation should be skipped when Redis is disabled."""
    monkeypatch.setenv("REDIS_ENABLED", "false")

    pool = await create_arq_pool()

    assert pool is None


@pytest.mark.asyncio
async def test_create_arq_pool_returns_pool_when_enabled(monkeypatch):
    """ARQ pool should be created from Redis DSN when Redis is enabled."""
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/9")
    mock_pool = AsyncMock()
    mock_pool.ping = AsyncMock()

    with patch(
        "app.api.main.create_pool", new=AsyncMock(return_value=mock_pool)
    ) as mock_create_pool:
        pool = await create_arq_pool()

    assert pool is mock_pool
    mock_create_pool.assert_awaited_once()
    mock_pool.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_daily_ohlc_job_uses_arq_when_available():
    """Daily updates should be enqueued to ARQ when a pool exists."""
    app = FastAPI()
    app.state.arq_pool = AsyncMock()

    with patch("app.api.main.update_daily_ohlc", new=AsyncMock()) as mock_update:
        await enqueue_daily_ohlc_job(app)

    app.state.arq_pool.enqueue_job.assert_awaited_once_with("update_daily_ohlc")
    mock_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_daily_ohlc_job_falls_back_without_arq():
    """Daily updates should run locally when ARQ is unavailable."""
    app = FastAPI()
    app.state.arq_pool = None

    with patch("app.api.main.update_daily_ohlc", new=AsyncMock()) as mock_update:
        await enqueue_daily_ohlc_job(app)

    mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_arq_pool_handles_async_close():
    """Pool close helper should await async closers."""
    pool = AsyncMock()

    await close_arq_pool(pool)

    pool.aclose.assert_awaited_once()
