# tests/test_dataflows_cache.py
from datetime import datetime

import pytest
import redis.exceptions

from app.dataflows.cache import CacheConfig, DataCache
from app.dataflows.models import StockCandle


@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Test cache set and get operations"""
    cache = DataCache("redis://localhost:6379")

    # Create test data
    candles = [
        StockCandle(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000000,
        )
    ]

    try:
        # Set cache
        await cache.set(
            "stock_data",
            candles,
            CacheConfig.STOCK_DATA_TTL,
            symbol="AAPL",
            start="2024-01-01",
            end="2024-01-31",
        )

        # Get cache
        cached = await cache.get("stock_data", symbol="AAPL", start="2024-01-01", end="2024-01-31")

        assert cached is not None
        assert len(cached) == 1
        assert cached[0]["open"] == 100.0
    except redis.exceptions.ConnectionError:
        pytest.skip("Redis not running")


@pytest.mark.asyncio
async def test_cache_miss():
    """Test cache miss returns None"""
    cache = DataCache("redis://localhost:6379")

    try:
        result = await cache.get("stock_data", symbol="NONEXISTENT", start="2024-01-01")

        assert result is None
    except redis.exceptions.ConnectionError:
        pytest.skip("Redis not running")
