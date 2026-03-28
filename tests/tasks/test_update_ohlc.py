"""Tests for ARQ-compatible OHLC update tasks."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.tasks.update_ohlc import update_daily_ohlc


@pytest.mark.asyncio
async def test_update_daily_ohlc_returns_summary_with_redis_ctx():
    """Task should return summary and write a lightweight marker into Redis ctx."""
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    with patch("app.tasks.update_ohlc.SYMBOLS", ["AAPL", "MSFT"]):
        with patch("app.tasks.update_ohlc.asyncio.to_thread", new=AsyncMock()) as mock_to_thread:

            def run_sync(func, *args, **kwargs):
                return func(*args, **kwargs)

            mock_to_thread.side_effect = run_sync

            with patch(
                "app.tasks.update_ohlc.call_get_stock_history",
                return_value=[{"date": "2026-03-25"}],
            ):
                with patch("app.tasks.update_ohlc.upsert_ohlc", new=Mock()) as mock_upsert:
                    with patch(
                        "app.tasks.update_ohlc.update_metadata", new=Mock()
                    ) as mock_update_metadata:
                        result = await update_daily_ohlc(ctx)

    assert result == {"success": 2, "failed": 0, "total_records": 2}
    assert mock_upsert.call_count == 2
    assert mock_update_metadata.call_count == 2
    assert mock_redis.set.await_count == 2


@pytest.mark.asyncio
async def test_update_daily_ohlc_counts_failures():
    """Task should continue processing when one symbol fails."""
    with patch("app.tasks.update_ohlc.SYMBOLS", ["AAPL", "MSFT"]):
        with patch("app.tasks.update_ohlc.asyncio.to_thread", new=AsyncMock()) as mock_to_thread:

            def run_sync(func, *args, **kwargs):
                return func(*args, **kwargs)

            mock_to_thread.side_effect = run_sync

            def fake_history(symbol, *_args):
                if symbol == "AAPL":
                    raise RuntimeError("boom")
                return [{"date": "2026-03-25"}]

            with patch("app.tasks.update_ohlc.call_get_stock_history", side_effect=fake_history):
                with patch("app.tasks.update_ohlc.upsert_ohlc", new=Mock()):
                    with patch("app.tasks.update_ohlc.update_metadata", new=Mock()):
                        result = await update_daily_ohlc()

    assert result == {"success": 1, "failed": 1, "total_records": 1}
