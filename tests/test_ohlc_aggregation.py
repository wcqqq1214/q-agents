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
    result = get_ohlc_aggregated('TEST', '2024-01-02', '2024-01-04', 'day')
    assert len(result) == 3
    assert result[0]['date'] == '2024-01-02'
    assert result[0]['open'] == 100.0
    assert result[0]['close'] == 103.0

def test_get_ohlc_aggregated_week(sample_data):
    """Test week interval aggregates by ISO week."""
    # Sample data spans one week (2024-01-02 to 2024-01-04 are Tue-Thu)
    result = get_ohlc_aggregated('TEST', '2024-01-01', '2024-01-07', 'week')
    assert len(result) == 1
    # Week should start on Monday 2024-01-01
    assert result[0]['date'] == '2024-01-01'
    assert result[0]['open'] == 100.0  # First day's open
    assert result[0]['high'] == 110.0  # Max of all highs
    assert result[0]['low'] == 99.0    # Min of all lows
    assert result[0]['close'] == 109.0 # Last day's close
    assert result[0]['volume'] == 3300000  # Sum of volumes
