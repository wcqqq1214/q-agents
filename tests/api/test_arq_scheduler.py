"""Tests for ARQ-backed scheduling helpers."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.api.main import (
    close_arq_pool,
    configure_daily_digest_job,
    configure_market_data_jobs,
    create_arq_pool,
    enqueue_daily_ohlc_job,
)


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

    app.state.arq_pool.enqueue_job.assert_awaited_once_with(
        "update_daily_ohlc", overwrite_existing=True
    )
    mock_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_daily_ohlc_job_falls_back_without_arq():
    """Daily updates should run locally when ARQ is unavailable."""
    app = FastAPI()
    app.state.arq_pool = None

    with patch("app.api.main.update_daily_ohlc", new=AsyncMock()) as mock_update:
        await enqueue_daily_ohlc_job(app)

    mock_update.assert_awaited_once_with(overwrite_existing=True)


@pytest.mark.asyncio
async def test_close_arq_pool_handles_async_close():
    """Pool close helper should await async closers."""
    pool = AsyncMock()

    await close_arq_pool(pool)

    pool.aclose.assert_awaited_once()


def test_configure_market_data_jobs_registers_5_minute_stock_jobs():
    """Stock scheduler should register intraday and post-close jobs at 5m/16:30 ET."""
    app = FastAPI()
    mock_scheduler = Mock()

    configure_market_data_jobs(app, mock_scheduler)

    intraday_call = next(
        call
        for call in mock_scheduler.add_job.call_args_list
        if call.kwargs["id"] == "intraday_stock_update"
    )
    post_close_call = next(
        call
        for call in mock_scheduler.add_job.call_args_list
        if call.kwargs["id"] == "daily_ohlc_update"
    )
    crypto_call = next(
        call
        for call in mock_scheduler.add_job.call_args_list
        if call.kwargs["id"] == "daily_crypto_download"
    )

    trigger = intraday_call.kwargs["trigger"]
    assert isinstance(trigger, CronTrigger)
    assert str(trigger.timezone) == "America/New_York"
    assert "1,6,11,16,21,26,31,36,41,46,51,56" in str(trigger)

    assert post_close_call.args[1] == "cron"
    assert post_close_call.kwargs["hour"] == 16
    assert post_close_call.kwargs["minute"] == 30

    crypto_trigger = crypto_call.kwargs["trigger"]
    assert isinstance(crypto_trigger, CronTrigger)
    assert str(crypto_trigger.timezone) == "UTC"


def test_configure_daily_digest_job_registers_cron_job(monkeypatch):
    """Daily digest scheduler should register a single cron job when enabled."""
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIME", "08:00")
    monkeypatch.setenv("DAILY_DIGEST_TIMEZONE", "Asia/Shanghai")
    app = FastAPI()
    scheduler = Mock()

    configure_daily_digest_job(app, scheduler)

    digest_call = next(
        call
        for call in scheduler.add_job.call_args_list
        if call.kwargs["id"] == "daily_email_digest"
    )
    assert digest_call.args[0].__name__ == "send_daily_digest"
    assert isinstance(digest_call.kwargs["trigger"], CronTrigger)
    assert str(digest_call.kwargs["trigger"].timezone) == "Asia/Shanghai"
    assert digest_call.kwargs["replace_existing"] is True
    assert digest_call.kwargs["max_instances"] == 1


def test_configure_daily_digest_job_skips_invalid_schedule(monkeypatch, caplog):
    """Daily digest scheduler should log and skip invalid schedule config."""
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIME", "99:99")
    app = FastAPI()
    scheduler = Mock()

    configure_daily_digest_job(app, scheduler)

    assert all(
        call.kwargs.get("id") != "daily_email_digest" for call in scheduler.add_job.call_args_list
    )
    assert (
        "Skipping daily digest registration because digest schedule config is invalid"
        in caplog.text
    )
