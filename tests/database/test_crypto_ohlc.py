"""Tests for crypto OHLC database operations."""

import pytest
from app.database.schema import get_conn


@pytest.fixture(autouse=True)
def clean_crypto_ohlc():
    """Clean crypto_ohlc table before each test."""
    conn = get_conn()
    conn.execute("DELETE FROM crypto_ohlc")
    conn.commit()
    conn.close()
    yield


def test_get_max_timestamp_with_data():
    """Test getting max timestamp when data exists."""
    from app.database.crypto_ohlc import upsert_crypto_ohlc, get_max_timestamp

    # Insert test data
    data = [
        {'timestamp': 1000000, 'date': '2020-01-01T00:00:00+00:00',
         'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000},
        {'timestamp': 2000000, 'date': '2020-01-01T00:01:00+00:00',
         'open': 105, 'high': 115, 'low': 95, 'close': 110, 'volume': 1100},
    ]
    upsert_crypto_ohlc('BTCUSDT', '1m', data)

    # Test
    max_ts = get_max_timestamp('BTCUSDT', '1m')
    assert max_ts == 2000000


def test_get_max_timestamp_no_data():
    """Test getting max timestamp when no data exists."""
    from app.database.crypto_ohlc import get_max_timestamp

    max_ts = get_max_timestamp('NONEXISTENT', '1m')
    assert max_ts is None


def test_get_max_date_with_data():
    """Test getting max date when data exists."""
    from app.database.crypto_ohlc import upsert_crypto_ohlc, get_max_date
    from datetime import date

    # Insert test data
    data = [
        {'timestamp': 1577836800000, 'date': '2020-01-01T00:00:00+00:00',
         'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000},
        {'timestamp': 1577923200000, 'date': '2020-01-02T00:00:00+00:00',
         'open': 105, 'high': 115, 'low': 95, 'close': 110, 'volume': 1100},
    ]
    upsert_crypto_ohlc('ETHUSDT', '1d', data)

    # Test
    max_date = get_max_date('ETHUSDT', '1d')
    assert max_date == date(2020, 1, 2)


def test_get_max_date_no_data():
    """Test getting max date when no data exists."""
    from app.database.crypto_ohlc import get_max_date

    max_date = get_max_date('NONEXISTENT', '1d')
    assert max_date is None
