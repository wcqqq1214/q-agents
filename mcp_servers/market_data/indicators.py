"""Technical indicators as pure functions on pandas Series.

Used by MCP get_stock_data tool. Kept here so the MCP server stays self-contained.
"""

from __future__ import annotations

from typing import Optional, TypedDict, cast

import pandas as pd


class MacdResult(TypedDict, total=False):
    """Last-bar MACD components."""

    macd_line: float
    signal: float
    histogram: float


class BollingerResult(TypedDict, total=False):
    """Last-bar Bollinger Bands."""

    middle: float
    upper: float
    lower: float


def sma(close: pd.Series, window: int) -> Optional[float]:
    """Simple moving average at last bar; None if not enough data."""
    if len(close) < window:
        return None
    mean_series = cast(pd.Series, close.rolling(window).mean())
    return float(mean_series.iloc[-1])


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average series."""
    return cast(pd.Series, close.ewm(span=span, adjust=False).mean())


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_span: int = 9,
) -> Optional[MacdResult]:
    """MACD line, signal, histogram at last bar. None if series too short."""
    if len(close) < slow + signal_span:
        return None
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_series = macd_line.ewm(span=signal_span, adjust=False).mean()
    hist = macd_line - signal_series
    return MacdResult(
        macd_line=float(macd_line.iloc[-1]),
        signal=float(signal_series.iloc[-1]),
        histogram=float(hist.iloc[-1]),
    )


def compute_bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> Optional[BollingerResult]:
    """Bollinger Bands at last bar. None if not enough data."""
    if len(close) < window:
        return None
    # Help type-checkers: explicitly cast rolling results to Series.
    middle = cast(pd.Series, close.rolling(window).mean())
    std = cast(pd.Series, close.rolling(window).std())
    upper = cast(pd.Series, middle + num_std * std)
    lower = cast(pd.Series, middle - num_std * std)
    return BollingerResult(
        middle=float(middle.iloc[-1]),
        upper=float(upper.iloc[-1]),
        lower=float(lower.iloc[-1]),
    )
