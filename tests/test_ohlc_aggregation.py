import pytest

from app.database.ohlc import get_ohlc_aggregated
from app.database.schema import get_conn


@pytest.fixture
def sample_data():
    """Insert sample OHLC data for testing."""
    conn = get_conn()
    conn.executescript("""
        DELETE FROM ohlc WHERE symbol = 'TEST';
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume) VALUES
        ('TEST', '2024-01-02', 100.0, 105.0, 99.0, 103.0, 1000000),
        ('TEST', '2024-01-03', 103.0, 108.0, 102.0, 107.0, 1100000),
        ('TEST', '2024-01-04', 107.0, 110.0, 106.0, 109.0, 1200000);
    """)
    conn.commit()
    conn.close()
    yield
    conn = get_conn()
    conn.execute("DELETE FROM ohlc WHERE symbol = 'TEST'")
    conn.commit()
    conn.close()


def test_get_ohlc_aggregated_day(sample_data):
    """Test day interval returns daily data unchanged."""
    result = get_ohlc_aggregated("TEST", "2024-01-02", "2024-01-04", "day")
    assert len(result) == 3
    assert result[0]["date"] == "2024-01-02"
    assert result[0]["open"] == 100.0
    assert result[0]["close"] == 103.0


def test_get_ohlc_aggregated_week(sample_data):
    """Test week interval aggregates by ISO week."""
    # Sample data spans one week (2024-01-02 to 2024-01-04 are Tue-Thu)
    result = get_ohlc_aggregated("TEST", "2024-01-01", "2024-01-07", "week")
    assert len(result) == 1
    # Week should start on Monday 2024-01-01
    assert result[0]["date"] == "2024-01-01"
    assert result[0]["open"] == 100.0  # First day's open
    assert result[0]["high"] == 110.0  # Max of all highs
    assert result[0]["low"] == 99.0  # Min of all lows
    assert result[0]["close"] == 109.0  # Last day's close
    assert result[0]["volume"] == 3300000  # Sum of volumes


@pytest.fixture
def multi_month_data():
    """Insert data spanning multiple months."""
    conn = get_conn()
    conn.executescript("""
        DELETE FROM ohlc WHERE symbol = 'TEST2';
        INSERT INTO ohlc (symbol, date, open, high, low, close, volume) VALUES
        ('TEST2', '2024-01-15', 100.0, 105.0, 99.0, 103.0, 1000000),
        ('TEST2', '2024-01-31', 103.0, 108.0, 102.0, 107.0, 1100000),
        ('TEST2', '2024-02-01', 107.0, 110.0, 106.0, 109.0, 1200000),
        ('TEST2', '2024-02-29', 109.0, 115.0, 108.0, 113.0, 1300000);
    """)
    conn.commit()
    conn.close()
    yield
    conn = get_conn()
    conn.execute("DELETE FROM ohlc WHERE symbol = 'TEST2'")
    conn.commit()
    conn.close()


def test_get_ohlc_aggregated_month(multi_month_data):
    """Test month interval aggregates by calendar month."""
    result = get_ohlc_aggregated("TEST2", "2024-01-01", "2024-02-29", "month")
    assert len(result) == 2
    # January
    assert result[0]["date"] == "2024-01-01"
    assert result[0]["open"] == 100.0
    assert result[0]["high"] == 108.0
    assert result[0]["low"] == 99.0
    assert result[0]["close"] == 107.0
    assert result[0]["volume"] == 2100000
    # February
    assert result[1]["date"] == "2024-02-01"
    assert result[1]["open"] == 107.0
    assert result[1]["close"] == 113.0


def test_get_ohlc_aggregated_year(multi_month_data):
    """Test year interval aggregates by calendar year."""
    result = get_ohlc_aggregated("TEST2", "2024-01-01", "2024-12-31", "year")
    assert len(result) == 1
    assert result[0]["date"] == "2024-01-01"
    assert result[0]["open"] == 100.0
    assert result[0]["high"] == 115.0
    assert result[0]["low"] == 99.0
    assert result[0]["close"] == 113.0
