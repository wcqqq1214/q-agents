"""Tests for stock updater helpers."""

from unittest.mock import patch

import pandas as pd

from app.services.stock_updater import _extract_symbol_frame, fetch_recent_ohlc


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
