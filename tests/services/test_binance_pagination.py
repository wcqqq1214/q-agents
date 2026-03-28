"""Tests for Binance K-line pagination logic."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.binance_client import fetch_klines_with_pagination


@pytest.mark.asyncio
async def test_single_batch_less_than_1000():
    """Test pagination with a single batch of less than 1000 records."""
    mock_data = [{"timestamp": i * 1000, "close": 100.0} for i in range(500)]

    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_data

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT", interval="1m", start_time=0, end_time=1000000
        )

        assert len(result) == 500
        assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_multiple_batches():
    """Test pagination with multiple batches of 1000 records."""
    batch1 = [{"timestamp": i * 1000, "close": 100.0} for i in range(1000)]
    batch2 = [{"timestamp": (1000 + i) * 1000, "close": 100.0} for i in range(1000)]
    batch3 = [{"timestamp": (2000 + i) * 1000, "close": 100.0} for i in range(500)]

    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = [batch1, batch2, batch3]

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT", interval="1m", start_time=0, end_time=3000000
        )

        assert len(result) == 2500
        assert mock_fetch.call_count == 3


@pytest.mark.asyncio
async def test_empty_response():
    """Test pagination with empty response."""
    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = []

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT", interval="1m", start_time=0, end_time=1000000
        )

        assert len(result) == 0
        assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_timestamp_increment():
    """Test that pagination correctly increments timestamp by 1."""
    batch1 = [{"timestamp": i * 1000, "close": 100.0} for i in range(1000)]
    batch2 = [{"timestamp": (1000 + i) * 1000, "close": 100.0} for i in range(500)]

    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = [batch1, batch2]

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT", interval="1m", start_time=0, end_time=2000000
        )

        assert len(result) == 1500
        assert mock_fetch.call_count == 2

        # Verify second call used last_timestamp + 1
        second_call_args = mock_fetch.call_args_list[1]
        assert second_call_args[1]["start_time"] == 999000 + 1


@pytest.mark.asyncio
async def test_stops_at_end_time():
    """Test that pagination stops when last_timestamp >= end_time."""
    batch1 = [{"timestamp": i * 1000, "close": 100.0} for i in range(1000)]

    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = batch1

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT",
            interval="1m",
            start_time=0,
            end_time=999000,  # Same as last timestamp
        )

        assert len(result) == 1000
        assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_fetch_klines_exactly_1000():
    """Test fetching exactly 1000 records (boundary case)."""
    mock_data = [{"timestamp": i * 1000, "close": 100.0} for i in range(1000)]

    with patch(
        "app.services.binance_client.fetch_binance_klines", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_data

        result = await fetch_klines_with_pagination(
            symbol="BTCUSDT", interval="1m", start_time=0, end_time=1000000
        )

        assert len(result) == 1000
        assert mock_fetch.call_count == 1
