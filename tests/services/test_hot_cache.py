"""
Tests for hot cache infrastructure for crypto K-line data.
"""
import asyncio
import pytest
import pandas as pd
from datetime import datetime, timezone
from app.services.hot_cache import (
    get_hot_cache,
    append_to_hot_cache,
    cleanup_hot_cache,
    get_cache_size,
    HOT_CACHE,
    clear_memory_cache,
)
from app.services.redis_client import reset_redis_state


@pytest.fixture(autouse=True)
def reset_hot_cache_state(monkeypatch):
    """Reset local cache and Redis state before each test."""
    monkeypatch.setenv("REDIS_ENABLED", "false")
    clear_memory_cache()
    asyncio.run(reset_redis_state())
    yield
    clear_memory_cache()
    asyncio.run(reset_redis_state())


class TestHotCacheInitialization:
    """Test hot cache initialization and structure."""

    def test_hot_cache_structure(self):
        """Test that HOT_CACHE has correct structure for BTCUSDT and ETHUSDT."""
        assert isinstance(HOT_CACHE, dict)
        assert "BTCUSDT" in HOT_CACHE
        assert "ETHUSDT" in HOT_CACHE
        assert isinstance(HOT_CACHE["BTCUSDT"], dict)
        assert isinstance(HOT_CACHE["ETHUSDT"], dict)


class TestGetHotCache:
    """Test get_hot_cache function."""

    def test_get_empty_cache_returns_empty_dataframe(self):
        """Test that getting non-existent cache returns empty DataFrame with correct columns."""
        df = get_hot_cache("BTCUSDT", "1m")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        expected_columns = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume']
        assert list(df.columns) == expected_columns

    def test_get_cache_returns_copy(self):
        """Test that get_hot_cache returns a copy, not reference."""
        # First, add some data
        test_data = pd.DataFrame({
            'timestamp': [1710000000],
            'date': [datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc)],
            'open': [50000.0],
            'high': [50100.0],
            'low': [49900.0],
            'close': [50050.0],
            'volume': [100.0]
        })
        append_to_hot_cache("BTCUSDT", "1m", test_data)

        # Get the cache
        df1 = get_hot_cache("BTCUSDT", "1m")
        df2 = get_hot_cache("BTCUSDT", "1m")

        # Modify df1
        df1.loc[0, 'close'] = 99999.0

        # df2 should not be affected
        assert df2.loc[0, 'close'] == 50050.0


class TestAppendToHotCache:
    """Test append_to_hot_cache function."""

    def test_append_to_empty_cache(self):
        """Test appending data to empty cache."""
        test_data = pd.DataFrame({
            'timestamp': [1710000000, 1710000060],
            'date': [
                datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc),
                datetime(2024, 3, 9, 12, 1, tzinfo=timezone.utc)
            ],
            'open': [50000.0, 50050.0],
            'high': [50100.0, 50150.0],
            'low': [49900.0, 49950.0],
            'close': [50050.0, 50100.0],
            'volume': [100.0, 150.0]
        })

        append_to_hot_cache("ETHUSDT", "5m", test_data)
        result = get_hot_cache("ETHUSDT", "5m")

        assert len(result) == 2
        assert result.loc[0, 'timestamp'] == 1710000000
        assert result.loc[1, 'timestamp'] == 1710000060

    def test_append_deduplication_keeps_last(self):
        """Test that deduplication keeps the last (newer) data."""
        # First batch
        data1 = pd.DataFrame({
            'timestamp': [1710000000],
            'date': [datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc)],
            'open': [50000.0],
            'high': [50100.0],
            'low': [49900.0],
            'close': [50050.0],
            'volume': [100.0]
        })
        append_to_hot_cache("BTCUSDT", "1m", data1)

        # Second batch with duplicate timestamp but different values
        data2 = pd.DataFrame({
            'timestamp': [1710000000],
            'date': [datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc)],
            'open': [50000.0],
            'high': [50200.0],  # Different high
            'low': [49900.0],
            'close': [50150.0],  # Different close
            'volume': [200.0]  # Different volume
        })
        append_to_hot_cache("BTCUSDT", "1m", data2)

        result = get_hot_cache("BTCUSDT", "1m")

        # Should have only 1 record with the newer values
        assert len(result) == 1
        assert result.loc[0, 'high'] == 50200.0
        assert result.loc[0, 'close'] == 50150.0
        assert result.loc[0, 'volume'] == 200.0

    def test_append_respects_max_records_limit(self):
        """Test that cache is limited to max_records (2880 by default)."""
        # Create 3000 records
        timestamps = list(range(1710000000, 1710000000 + 3000 * 60, 60))
        dates = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in timestamps]

        test_data = pd.DataFrame({
            'timestamp': timestamps,
            'date': dates,
            'open': [50000.0] * 3000,
            'high': [50100.0] * 3000,
            'low': [49900.0] * 3000,
            'close': [50050.0] * 3000,
            'volume': [100.0] * 3000
        })

        append_to_hot_cache("BTCUSDT", "1m", test_data)
        result = get_hot_cache("BTCUSDT", "1m")

        # Should be limited to 2880 records
        assert len(result) == 2880
        # Should keep the most recent records
        assert result.loc[0, 'timestamp'] == timestamps[-2880]
        assert result.loc[2879, 'timestamp'] == timestamps[-1]

    def test_append_sorts_by_timestamp(self):
        """Test that data is sorted by timestamp after append."""
        # Add data out of order
        data1 = pd.DataFrame({
            'timestamp': [1710000120],
            'date': [datetime(2024, 3, 9, 12, 2, tzinfo=timezone.utc)],
            'open': [50100.0],
            'high': [50200.0],
            'low': [50000.0],
            'close': [50150.0],
            'volume': [150.0]
        })
        append_to_hot_cache("ETHUSDT", "1m", data1)

        data2 = pd.DataFrame({
            'timestamp': [1710000000],
            'date': [datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc)],
            'open': [50000.0],
            'high': [50100.0],
            'low': [49900.0],
            'close': [50050.0],
            'volume': [100.0]
        })
        append_to_hot_cache("ETHUSDT", "1m", data2)

        result = get_hot_cache("ETHUSDT", "1m")

        # Should be sorted
        assert len(result) == 2
        assert result.loc[0, 'timestamp'] == 1710000000
        assert result.loc[1, 'timestamp'] == 1710000120


class TestCleanupHotCache:
    """Test cleanup_hot_cache function."""

    def test_cleanup_removes_old_data(self):
        """Test that cleanup removes data before cutoff date."""
        # Add data spanning multiple days (use millisecond timestamps like Binance)
        timestamps = [1710000000000, 1710086400000, 1710172800000]  # 3 days apart
        dates = [datetime.fromtimestamp(ts / 1000, tz=timezone.utc) for ts in timestamps]

        test_data = pd.DataFrame({
            'timestamp': timestamps,
            'date': dates,
            'open': [50000.0, 51000.0, 52000.0],
            'high': [50100.0, 51100.0, 52100.0],
            'low': [49900.0, 50900.0, 51900.0],
            'close': [50050.0, 51050.0, 52050.0],
            'volume': [100.0, 150.0, 200.0]
        })

        append_to_hot_cache("BTCUSDT", "1h", test_data)

        # Cleanup data before the second date
        cutoff = datetime.fromtimestamp(1710086400, tz=timezone.utc)
        cleanup_hot_cache("BTCUSDT", "1h", cutoff)

        result = get_hot_cache("BTCUSDT", "1h")

        # Should only have 2 records (from cutoff onwards)
        assert len(result) == 2
        assert result.loc[0, 'timestamp'] == 1710086400000
        assert result.loc[1, 'timestamp'] == 1710172800000

    def test_cleanup_empty_cache(self):
        """Test cleanup on empty cache doesn't error."""
        cutoff = datetime(2024, 3, 9, tzinfo=timezone.utc)
        # Should not raise any errors
        cleanup_hot_cache("BTCUSDT", "15m", cutoff)

    def test_cleanup_nonexistent_symbol(self):
        """Test cleanup on non-existent symbol doesn't error."""
        cutoff = datetime(2024, 3, 9, tzinfo=timezone.utc)
        # Should not raise any errors
        cleanup_hot_cache("XRPUSDT", "1m", cutoff)


class TestGetCacheSize:
    """Test get_cache_size function."""

    def test_empty_cache_size_is_zero(self):
        """Test that empty cache has zero size."""
        # Clear all caches first
        for symbol in HOT_CACHE:
            HOT_CACHE[symbol] = {}

        size = get_cache_size()
        assert size == 0

    def test_cache_size_increases_with_data(self):
        """Test that cache size increases when data is added."""
        # Clear all caches first
        for symbol in HOT_CACHE:
            HOT_CACHE[symbol] = {}

        initial_size = get_cache_size()

        # Add some data
        test_data = pd.DataFrame({
            'timestamp': list(range(1710000000, 1710000000 + 100 * 60, 60)),
            'date': [datetime.fromtimestamp(ts, tz=timezone.utc)
                    for ts in range(1710000000, 1710000000 + 100 * 60, 60)],
            'open': [50000.0] * 100,
            'high': [50100.0] * 100,
            'low': [49900.0] * 100,
            'close': [50050.0] * 100,
            'volume': [100.0] * 100
        })

        append_to_hot_cache("BTCUSDT", "1m", test_data)
        size_after = get_cache_size()

        assert size_after > initial_size
        assert size_after > 0

    def test_cache_size_accounts_for_multiple_symbols(self):
        """Test that cache size accounts for all symbols and intervals."""
        # Clear all caches first
        for symbol in HOT_CACHE:
            HOT_CACHE[symbol] = {}

        test_data = pd.DataFrame({
            'timestamp': [1710000000],
            'date': [datetime(2024, 3, 9, 12, 0, tzinfo=timezone.utc)],
            'open': [50000.0],
            'high': [50100.0],
            'low': [49900.0],
            'close': [50050.0],
            'volume': [100.0]
        })

        append_to_hot_cache("BTCUSDT", "1m", test_data)
        size_one = get_cache_size()

        append_to_hot_cache("ETHUSDT", "1m", test_data)
        size_two = get_cache_size()

        # Size should increase
        assert size_two > size_one
