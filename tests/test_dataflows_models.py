import pytest
from datetime import datetime
from app.dataflows.models import StockCandle

def test_stock_candle_valid():
    """Test valid OHLCV data"""
    candle = StockCandle(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 1),
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000000
    )
    assert candle.high >= candle.low
    assert candle.volume >= 0

def test_stock_candle_invalid_high_low():
    """Test high < low raises error"""
    with pytest.raises(ValueError, match="high must be >= low"):
        StockCandle(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=99.0,  # Invalid: high < low
            low=105.0,
            close=103.0,
            volume=1000000
        )

def test_stock_candle_negative_volume():
    """Test negative volume raises error"""
    with pytest.raises(ValueError, match="volume must be >= 0"):
        StockCandle(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=-1000  # Invalid
        )
