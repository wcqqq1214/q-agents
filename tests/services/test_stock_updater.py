"""Tests for stock updater helpers."""

from unittest.mock import patch

import pandas as pd

from app.services.stock_updater import (
    _extract_symbol_frame,
    fetch_recent_ohlc,
    update_stocks_intraday_sync,
)


def test_extract_symbol_frame_single_symbol_multiindex():
    """Single-symbol yfinance output should drop the symbol level."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Open", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    data = pd.DataFrame(
        [[1.0, 2.0, 0.5, 1.5, 100]],
        index=pd.Index(["2026-03-24"]),
        columns=columns,
    )

    frame = _extract_symbol_frame(data, "AAPL", 1)

    assert list(frame.columns) == ["Close", "High", "Low", "Open", "Volume"]
    assert frame.loc["2026-03-24", "Close"] == 1.0


def test_extract_symbol_frame_multi_symbol_multiindex_level_zero():
    """Multi-symbol yfinance output should select the requested symbol."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Open"),
            ("AAPL", "Close"),
            ("MSFT", "Open"),
            ("MSFT", "Close"),
        ]
    )
    data = pd.DataFrame(
        [[1.5, 1.0, 2.5, 2.0]],
        index=pd.Index(["2026-03-24"]),
        columns=columns,
    )

    frame = _extract_symbol_frame(data, "AAPL", 2)

    assert list(frame.columns) == ["Open", "Close"]
    assert frame.loc["2026-03-24", "Open"] == 1.5


def test_extract_symbol_frame_multi_symbol_multiindex_level_one_fallback():
    """Fallback path should also handle level-1 symbol layout."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAPL"),
            ("Open", "AAPL"),
            ("Close", "MSFT"),
            ("Open", "MSFT"),
        ]
    )
    data = pd.DataFrame(
        [[1.0, 1.5, 2.0, 2.5]],
        index=pd.Index(["2026-03-24"]),
        columns=columns,
    )

    frame = _extract_symbol_frame(data, "MSFT", 2)

    assert list(frame.columns) == ["Close", "Open"]
    assert frame.loc["2026-03-24", "Close"] == 2.0


def test_fetch_recent_ohlc_single_symbol_multiindex():
    """fetch_recent_ohlc should handle single-symbol MultiIndex output."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Open", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    data = pd.DataFrame(
        [[1.0, 2.0, 0.5, 1.5, 100]],
        index=pd.DatetimeIndex(["2026-03-24"], tz="UTC"),
        columns=columns,
    )

    with patch("app.services.stock_updater.yf.download", return_value=data):
        result = fetch_recent_ohlc(["AAPL"], days=2)

    assert result["AAPL"][0]["date"] == "2026-03-24"
    assert result["AAPL"][0]["close"] == 1.0


def test_fetch_recent_ohlc_multi_symbol_multiindex():
    """fetch_recent_ohlc should handle multi-symbol MultiIndex output."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Open"),
            ("AAPL", "Close"),
            ("AAPL", "High"),
            ("AAPL", "Low"),
            ("AAPL", "Volume"),
            ("MSFT", "Open"),
            ("MSFT", "Close"),
            ("MSFT", "High"),
            ("MSFT", "Low"),
            ("MSFT", "Volume"),
        ]
    )
    data = pd.DataFrame(
        [[1.5, 1.0, 2.0, 0.5, 100, 2.5, 2.0, 3.0, 1.5, 200]],
        index=pd.DatetimeIndex(["2026-03-24"], tz="UTC"),
        columns=columns,
    )

    with patch("app.services.stock_updater.yf.download", return_value=data):
        result = fetch_recent_ohlc(["AAPL", "MSFT"], days=2)

    assert result["AAPL"][0]["close"] == 1.0
    assert result["MSFT"][0]["close"] == 2.0


def test_fetch_recent_ohlc_batches_symbols_in_single_download_call():
    """fetch_recent_ohlc should batch requested symbols into one download call."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Open"),
            ("AAPL", "Close"),
            ("AAPL", "High"),
            ("AAPL", "Low"),
            ("AAPL", "Volume"),
            ("MSFT", "Open"),
            ("MSFT", "Close"),
            ("MSFT", "High"),
            ("MSFT", "Low"),
            ("MSFT", "Volume"),
        ]
    )
    data = pd.DataFrame(
        [[1.5, 1.0, 2.0, 0.5, 100, 2.5, 2.0, 3.0, 1.5, 200]],
        index=pd.DatetimeIndex(["2026-03-24"], tz="UTC"),
        columns=columns,
    )

    with patch("app.services.stock_updater.yf.download", return_value=data) as mock_download:
        fetch_recent_ohlc(["AAPL", "MSFT"], days=5)

    mock_download.assert_called_once()
    assert mock_download.call_args.kwargs["tickers"] == ["AAPL", "MSFT"]


def test_update_stocks_intraday_sync_prefers_mcp_history_over_yfinance():
    """Intraday stock refresh should use MCP history so rate-limited yfinance is bypassed."""
    columns = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Open", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    yfinance_frame = pd.DataFrame(
        [[258.03, 259.75, 256.53, 258.51, 16640495]],
        index=pd.DatetimeIndex(["2026-04-08"], tz="UTC"),
        columns=columns,
    )
    mcp_rows = [
        {
            "date": "2026-04-08",
            "open": 258.51,
            "high": 259.75,
            "low": 256.53,
            "close": 258.03,
            "volume": 16640495,
        }
    ]

    with patch("app.services.stock_updater.should_update_stocks", return_value=True):
        with patch("app.services.stock_updater.SYMBOLS", ["AAPL"]):
            with patch("app.database.upsert_ohlc_overwrite") as mock_upsert:
                with patch("app.database.update_metadata") as mock_update_metadata:
                    with patch(
                        "app.mcp_client.finance_client.call_get_stock_history",
                        return_value=mcp_rows,
                    ) as mock_history:
                        with patch(
                            "app.services.stock_updater.yf.download",
                            return_value=yfinance_frame,
                        ) as mock_download:
                            update_stocks_intraday_sync()

    mock_history.assert_called_once()
    mock_download.assert_not_called()
    mock_upsert.assert_called_once_with("AAPL", mcp_rows)
    mock_update_metadata.assert_called_once_with("AAPL", "2026-04-08", "2026-04-08")


def test_update_stocks_intraday_sync_synthesizes_market_day_row_from_quote():
    """When MCP history lags, intraday refresh should append a quote-derived market-day candle."""
    stale_history_rows = [
        {
            "date": "2026-04-07",
            "open": 256.16,
            "high": 256.2,
            "low": 245.7,
            "close": 253.5,
            "volume": 61377300,
        }
    ]

    with patch("app.services.stock_updater.should_update_stocks", return_value=True):
        with patch("app.services.stock_updater.SYMBOLS", ["AAPL"]):
            with patch(
                "app.services.stock_updater.get_current_market_date",
                return_value=pd.Timestamp("2026-04-08").date(),
            ):
                with patch("app.database.upsert_ohlc_overwrite") as mock_upsert:
                    with patch("app.database.update_metadata") as mock_update_metadata:
                        with patch(
                            "app.mcp_client.finance_client.call_get_stock_history",
                            return_value=stale_history_rows,
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
                                update_stocks_intraday_sync()

    written_rows = mock_upsert.call_args.args[1]
    assert written_rows[-1]["date"] == "2026-04-08"
    assert written_rows[-1]["close"] == 257.79
    assert written_rows[-1]["open"] == 258.51
    assert written_rows[-1]["high"] == 259.75
    assert written_rows[-1]["low"] == 256.53
    assert written_rows[-1]["volume"] == 18546365
    mock_update_metadata.assert_called_once_with("AAPL", "2026-04-07", "2026-04-08")
