"""Regression coverage for stock OHLC route freshness fallback."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.api.routes.ohlc import get_stock_ohlc_from_db


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = datetime(2026, 4, 9, 0, 6, tzinfo=ZoneInfo("Asia/Shanghai"))
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


def test_get_stock_ohlc_from_db_uses_est_market_date_for_fallback_window():
    """Fallback fetch should target the current America/New_York trading date."""
    stale_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        }
    ]
    fresh_rows = [
        {
            "date": "2026-04-08",
            "open": 258.51,
            "high": 259.75,
            "low": 256.53,
            "close": 258.03,
            "volume": 16640495,
        }
    ]

    with patch("app.api.routes.ohlc.datetime", _FixedDateTime):
        with patch("app.api.routes.ohlc.get_ohlc_aggregated", side_effect=[stale_rows, stale_rows]):
            with patch("app.database.get_ohlc", return_value=stale_rows):
                with patch("app.database.upsert_ohlc_overwrite"):
                    with patch("app.database.update_metadata"):
                        with patch(
                            "app.mcp_client.finance_client.call_get_stock_history",
                            return_value=fresh_rows,
                        ) as mock_history:
                            get_stock_ohlc_from_db("AAPL", interval="day")

    assert mock_history.call_args is not None
    assert mock_history.call_args.args[2] == "2026-04-08"


def test_get_stock_ohlc_from_db_refreshes_stale_daily_rows():
    """Stale daily DB results should be healed with a newer MCP daily row."""
    stale_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        }
    ]
    refreshed_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        },
        {
            "date": "2026-04-08",
            "open": 258.51,
            "high": 259.75,
            "low": 256.53,
            "close": 258.03,
            "volume": 16640495,
        },
    ]

    with patch("app.api.routes.ohlc.datetime", _FixedDateTime):
        with patch(
            "app.api.routes.ohlc.get_ohlc_aggregated",
            side_effect=[stale_rows, refreshed_rows],
        ):
            with patch("app.database.get_ohlc", return_value=stale_rows):
                with patch("app.database.upsert_ohlc_overwrite"):
                    with patch("app.database.update_metadata"):
                        with patch(
                            "app.mcp_client.finance_client.call_get_stock_history",
                            return_value=refreshed_rows,
                        ):
                            response = get_stock_ohlc_from_db("AAPL", interval="day")

    assert [row.date for row in response.data] == ["2026-04-07", "2026-04-08"]


def test_get_stock_ohlc_from_db_synthesizes_market_day_row_from_quote_when_history_lags():
    """If MCP history still lags, the route should synthesize the current market-day candle from quote data."""
    stale_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        }
    ]
    refreshed_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        },
        {
            "date": "2026-04-08",
            "open": 258.51,
            "high": 259.75,
            "low": 256.53,
            "close": 257.79,
            "volume": 18546365,
        },
    ]

    with patch("app.api.routes.ohlc.datetime", _FixedDateTime):
        with patch(
            "app.api.routes.ohlc.get_ohlc_aggregated",
            side_effect=[stale_rows, refreshed_rows],
        ):
            with patch("app.database.get_ohlc", return_value=stale_rows):
                with patch("app.database.upsert_ohlc_overwrite") as mock_upsert:
                    with patch("app.database.update_metadata"):
                        with patch(
                            "app.mcp_client.finance_client.call_get_stock_history",
                            return_value=stale_rows,
                        ):
                            with patch(
                                "app.mcp_client.finance_client.call_get_us_stock_quote",
                                return_value={
                                    "price": 257.79,
                                    "previous_close": 253.5,
                                    "open": 258.51,
                                    "day_high": 259.75,
                                    "day_low": 256.53,
                                    "volume": 18546365,
                                },
                            ):
                                response = get_stock_ohlc_from_db("AAPL", interval="day")

    assert [row.date for row in response.data] == ["2026-04-07", "2026-04-08"]
    written_rows = mock_upsert.call_args.args[1]
    assert written_rows[-1]["date"] == "2026-04-08"
