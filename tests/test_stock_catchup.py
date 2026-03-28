"""Unit tests for stock catchup mechanism."""

from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_metadata_current():
    """Mock metadata showing current data."""
    yesterday = date.today() - timedelta(days=1)
    return {
        "symbol": "AAPL",
        "last_update": datetime.now().isoformat(),
        "data_start": "2021-01-01",
        "data_end": yesterday.isoformat(),
    }


@pytest.fixture
def mock_metadata_gap():
    """Mock metadata showing 3-day gap."""
    three_days_ago = date.today() - timedelta(days=3)
    return {
        "symbol": "AAPL",
        "last_update": datetime.now().isoformat(),
        "data_start": "2021-01-01",
        "data_end": three_days_ago.isoformat(),
    }


@pytest.fixture
def mock_stock_data():
    """Mock stock OHLC data."""
    return {
        "AAPL": [
            {
                "date": "2026-03-24",
                "open": 180.0,
                "high": 182.0,
                "low": 179.0,
                "close": 181.0,
                "volume": 1000000,
            },
            {
                "date": "2026-03-25",
                "open": 181.0,
                "high": 183.0,
                "low": 180.0,
                "close": 182.0,
                "volume": 1100000,
            },
        ]
    }


@pytest.mark.asyncio
async def test_catchup_no_gap(mock_metadata_current):
    """Test catchup skips when data is current."""
    from app.services.stock_updater import catchup_historical_stocks

    with patch("app.database.ohlc.get_metadata", return_value=mock_metadata_current):
        stats = await catchup_historical_stocks(days=5)

        assert stats["symbols_updated"] == 0
        assert stats["records_added"] == 0
        assert stats["date_range"] is None
        assert stats["errors"] == []


@pytest.mark.asyncio
async def test_catchup_with_gap(mock_metadata_gap, mock_stock_data):
    """Test catchup fills gap correctly."""
    from app.services.stock_updater import catchup_historical_stocks

    with (
        patch("app.database.ohlc.get_metadata", return_value=mock_metadata_gap),
        patch(
            "app.services.stock_updater._fetch_with_rate_limit",
            return_value=mock_stock_data,
        ),
        patch("app.database.ohlc.upsert_ohlc_overwrite"),
        patch("app.database.ohlc.update_metadata"),
        patch(
            "app.config_manager.get_stock_catchup_config",
            return_value={"rate_limit_delay": 0.1},
        ),
    ):
        stats = await catchup_historical_stocks(days=5)

        assert stats["symbols_updated"] == 1
        assert stats["records_added"] == 2
        assert stats["date_range"] == ("2026-03-24", "2026-03-25")
        assert stats["errors"] == []


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting delays between requests."""
    from app.services.stock_updater import _fetch_with_rate_limit

    mock_fetch = Mock(return_value={"AAPL": [{"date": "2026-03-26", "close": 180.0}]})

    with patch("app.services.stock_updater.fetch_recent_ohlc", mock_fetch):
        start = datetime.now()
        await _fetch_with_rate_limit(["AAPL", "MSFT"], days=2, delay=0.5)
        elapsed = (datetime.now() - start).total_seconds()

        # Should have at least 0.5s delay between 2 symbols
        assert elapsed >= 0.5, f"Expected >= 0.5s, got {elapsed}s"


@pytest.mark.asyncio
async def test_force_bypass():
    """Test force=True bypasses trading hours check."""
    from app.services.stock_updater import update_stocks_intraday

    with (
        patch("app.services.stock_updater.should_update_stocks", return_value=False),
        patch("app.services.stock_updater.update_stocks_intraday_sync") as mock_sync,
    ):
        # force=False should skip
        await update_stocks_intraday(force=False)
        mock_sync.assert_not_called()

        # force=True should proceed
        await update_stocks_intraday(force=True)
        mock_sync.assert_called_once()
