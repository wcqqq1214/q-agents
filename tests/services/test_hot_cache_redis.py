"""Tests for Redis-backed hot cache behaviour."""

import asyncio
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import redis

from app.services.hot_cache import (
    HOT_CACHE,
    _serialize_dataframe,
    append_to_hot_cache,
    clear_memory_cache,
    get_hot_cache,
)
from app.services.redis_client import reset_redis_state


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "true")
    clear_memory_cache()
    asyncio.run(reset_redis_state())
    yield
    clear_memory_cache()
    asyncio.run(reset_redis_state())


def test_get_hot_cache_reads_from_redis():
    """Reads should prefer Redis payloads when available."""
    df = pd.DataFrame(
        [
            {
                "timestamp": 1710000000000,
                "date": "2024-03-09T12:00:00+00:00",
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 100.0,
            }
        ]
    )
    mock_client = Mock()
    mock_client.get.return_value = _serialize_dataframe(df)

    with patch("app.services.hot_cache.get_sync_redis_client", return_value=mock_client):
        result = get_hot_cache("BTCUSDT", "1m")

    assert len(result) == 1
    assert result.iloc[0]["close"] == 50050.0
    assert HOT_CACHE["BTCUSDT"] == {}


def test_append_to_hot_cache_falls_back_to_memory_on_redis_error():
    """Writes should degrade to memory cache when Redis is unavailable."""
    mock_client = Mock()
    mock_client.get.side_effect = redis.ConnectionError("redis down")

    with patch("app.services.hot_cache.get_sync_redis_client", return_value=mock_client):
        append_to_hot_cache(
            "BTCUSDT",
            "1m",
            [
                {
                    "timestamp": 1710000000000,
                    "date": "2024-03-09T12:00:00+00:00",
                    "open": 50000.0,
                    "high": 50100.0,
                    "low": 49900.0,
                    "close": 50050.0,
                    "volume": 100.0,
                }
            ],
        )

        # Read from memory cache while Redis is still mocked as unavailable
        result = get_hot_cache("BTCUSDT", "1m")
        assert len(result) == 1
        assert result.iloc[0]["close"] == 50050.0
