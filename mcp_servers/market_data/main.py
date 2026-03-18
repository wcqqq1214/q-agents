"""MCP server exposing Yahoo Finance stock quote and historical data via MCP tools."""

from __future__ import annotations

import sys
from pathlib import Path

# When run as script, ensure project root is on path
if __name__ != "__main__" or getattr(sys, "frozen", False):
    _root = None
else:
    _root = Path(__file__).resolve().parents[2]
    if _root and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables from .env file
load_dotenv()

from mcp_servers.market_data.indicators import (
    compute_bollinger_bands,
    compute_macd,
    sma,
)

mcp = FastMCP("market-data-server", json_response=True)


def _now_iso_utc8() -> str:
    """Return current time in ISO8601 format using UTC+8 without microseconds."""
    return (
        datetime.now(timezone.utc)
        .astimezone(timezone(timedelta(hours=8)))
        .replace(microsecond=0)
        .isoformat()
    )


def _round_or_none(value: Optional[float], ndigits: int = 3) -> Optional[float]:
    """Round a float to the given number of digits if not None."""
    if value is None:
        return None
    try:
        return round(value, ndigits)
    except (TypeError, ValueError):
        return None


def _fetch_quote_impl(ticker: str) -> dict[str, Any]:
    """Internal implementation of stock quote fetch using yfinance."""
    normalized = ticker.strip().upper() if ticker else ""
    if not normalized:
        return {
            "symbol": "",
            "currency": None,
            "price": None,
            "change": None,
            "change_percent": None,
            "previous_close": None,
            "open": None,
            "day_high": None,
            "day_low": None,
            "volume": None,
            "fifty_two_week_high": None,
            "fifty_two_week_low": None,
            "market_cap": None,
            "timestamp": _now_iso_utc8(),
            "error": (
                "Ticker symbol is empty. Please provide a valid US stock "
                "ticker such as 'AAPL' or 'MSFT'."
            ),
        }

    quote: dict[str, Any] = {
        "symbol": normalized,
        "currency": None,
        "price": None,
        "change": None,
        "change_percent": None,
        "previous_close": None,
        "open": None,
        "day_high": None,
        "day_low": None,
        "volume": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "market_cap": None,
        "timestamp": None,
    }

    try:
        yf_ticker = yf.Ticker(normalized)
        fast_info: Any = getattr(yf_ticker, "fast_info", None)
        history = yf_ticker.history(period="2d", interval="1d", auto_adjust=False)

        price: Optional[float] = None
        previous_close: Optional[float] = None
        open_price: Optional[float] = None
        day_high: Optional[float] = None
        day_low: Optional[float] = None
        volume: Optional[float] = None

        if not history.empty:
            latest = history.iloc[-1]
            day_high = float(latest.get("High")) if "High" in latest else None
            day_low = float(latest.get("Low")) if "Low" in latest else None
            price = float(latest.get("Close")) if "Close" in latest else None
            if "Volume" in latest:
                volume = float(latest.get("Volume"))

            if len(history.index) > 1:
                prev = history.iloc[-2]
                previous_close = (
                    float(prev.get("Close")) if "Close" in prev else None
                )

        def _get_fast(field_name: str, attr_name: str) -> Optional[float]:
            if fast_info is None:
                return None
            if hasattr(fast_info, attr_name):
                value = getattr(fast_info, attr_name)
            elif isinstance(fast_info, dict):
                value = fast_info.get(field_name)
            else:
                value = None
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        if price is None:
            price = _get_fast("lastPrice", "last_price")
        if previous_close is None:
            previous_close = _get_fast("previousClose", "previous_close")
        if open_price is None:
            open_price = _get_fast("open", "open")
        if day_high is None:
            day_high = _get_fast("dayHigh", "day_high")
        if day_low is None:
            day_low = _get_fast("dayLow", "day_low")
        if volume is None:
            volume = _get_fast("lastVolume", "last_volume")

        # 52-week range and market cap: prefer FastInfo (year_high/year_low ≈ 52w on Yahoo)
        fifty_two_week_high: Optional[float] = None
        fifty_two_week_low: Optional[float] = None
        market_cap: Optional[int] = None

        if fast_info is not None:
            if hasattr(fast_info, "currency"):
                quote["currency"] = getattr(fast_info, "currency")
            elif isinstance(fast_info, dict):
                quote["currency"] = fast_info.get("currency")

            # FastInfo exposes year_high/year_low/market_cap (see yfinance.scrapers.quote.FastInfo)
            for attr_high, attr_low in (
                ("year_high", "year_low"),
                ("fifty_two_week_high", "fifty_two_week_low"),
            ):
                if fifty_two_week_high is None and hasattr(fast_info, attr_high):
                    try:
                        fifty_two_week_high = float(getattr(fast_info, attr_high))
                    except (TypeError, ValueError):
                        pass
                if fifty_two_week_low is None and hasattr(fast_info, attr_low):
                    try:
                        fifty_two_week_low = float(getattr(fast_info, attr_low))
                    except (TypeError, ValueError):
                        pass
            if isinstance(fast_info, dict):
                fifty_two_week_high = fifty_two_week_high or _get_fast(
                    "fiftyTwoWeekHigh", "fifty_two_week_high"
                ) or _get_fast("yearHigh", "year_high")
                fifty_two_week_low = fifty_two_week_low or _get_fast(
                    "fiftyTwoWeekLow", "fifty_two_week_low"
                ) or _get_fast("yearLow", "year_low")
            if hasattr(fast_info, "market_cap"):
                try:
                    mc = getattr(fast_info, "market_cap")
                    if mc is not None:
                        market_cap = int(mc)
                except (TypeError, ValueError):
                    pass
            elif isinstance(fast_info, dict) and fast_info.get("marketCap") is not None:
                try:
                    market_cap = int(fast_info["marketCap"])
                except (TypeError, ValueError):
                    pass

        # Fallback: full info dict (slower) for 52w / market cap if still missing
        if (
            fifty_two_week_high is None
            or fifty_two_week_low is None
            or market_cap is None
        ):
            try:
                info = getattr(yf_ticker, "info", None) or {}
                if info:
                    if fifty_two_week_high is None and info.get("fiftyTwoWeekHigh") is not None:
                        fifty_two_week_high = _round_or_none(
                            float(info["fiftyTwoWeekHigh"]), 3
                        )
                    if fifty_two_week_low is None and info.get("fiftyTwoWeekLow") is not None:
                        fifty_two_week_low = _round_or_none(
                            float(info["fiftyTwoWeekLow"]), 3
                        )
                    if market_cap is None and info.get("marketCap") is not None:
                        try:
                            market_cap = int(info["marketCap"])
                        except (TypeError, ValueError):
                            pass
            except Exception:
                pass

        fifty_two_week_high = _round_or_none(fifty_two_week_high, 3)
        fifty_two_week_low = _round_or_none(fifty_two_week_low, 3)

        change: Optional[float] = None
        change_percent: Optional[float] = None
        if price is not None and previous_close not in (None, 0):
            change = price - previous_close
            try:
                change_percent = (change / previous_close) * 100
            except TypeError:
                pass

        price = _round_or_none(price, 3)
        previous_close = _round_or_none(previous_close, 3)
        open_price = _round_or_none(open_price, 3)
        day_high = _round_or_none(day_high, 3)
        day_low = _round_or_none(day_low, 3)
        change = _round_or_none(change, 3)
        change_percent = _round_or_none(change_percent, 2)
        if volume is not None:
            try:
                volume = int(volume)
            except (TypeError, ValueError):
                volume = None

        quote.update({
            "price": price,
            "previous_close": previous_close,
            "open": open_price,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "change": change,
            "change_percent": change_percent,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "market_cap": market_cap,
            "timestamp": _now_iso_utc8(),
        })

        if (
            quote["price"] is None
            and quote.get("previous_close") is None
            and quote.get("open") is None
        ):
            quote["error"] = (
                "No quote data available for the specified ticker. "
                "The symbol may be invalid or data may be temporarily unavailable."
            )

    except Exception as exc:
        quote["error"] = (
            f"Failed to fetch quote data from Yahoo Finance: "
            f"{type(exc).__name__}: {exc}"
        )
        quote["timestamp"] = _now_iso_utc8()

    return quote


@mcp.tool()
def get_us_stock_quote(ticker: str) -> dict[str, Any]:
    """Fetch the latest quote for a single US stock ticker using Yahoo Finance.

    This tool retrieves the most recent market data for a US-listed equity.
    Use it when the user asks for the latest price, price change, or intraday
    statistics about a stock such as AAPL or MSFT.

    Args:
        ticker: The US stock ticker symbol to query (e.g. AAPL, MSFT, GOOGL).

    Returns:
        A dict with symbol, currency, price, change, change_percent,
        previous_close, open, day_high, day_low, volume,
        fifty_two_week_high, fifty_two_week_low, market_cap, timestamp.
        May include an error field if the quote could not be retrieved.
    """
    return _fetch_quote_impl(ticker)


def _get_stock_data_impl(ticker: str, period: str = "3mo") -> dict[str, Any]:
    """Fetch history via yfinance and compute SMA, MACD, Bollinger; return last-bar snapshot."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        return {"ticker": "", "error": "Empty ticker."}

    try:
        t = yf.Ticker(normalized)
        hist = t.history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return {
                "ticker": normalized,
                "error": "No history returned for this ticker/period.",
            }

        close = cast(pd.Series, hist["Close"].astype(float))
        sma_20_val = sma(close, 20)
        macd_result = compute_macd(close)
        bb_result = compute_bollinger_bands(close, window=20, num_std=2.0)

        last_close = float(close.iloc[-1])
        return {
            "ticker": normalized,
            "last_close": last_close,
            "sma_20": sma_20_val,
            "macd_line": macd_result.get("macd_line") if macd_result else None,
            "macd_signal": macd_result.get("signal") if macd_result else None,
            "macd_histogram": macd_result.get("histogram") if macd_result else None,
            "bb_middle": bb_result.get("middle") if bb_result else None,
            "bb_upper": bb_result.get("upper") if bb_result else None,
            "bb_lower": bb_result.get("lower") if bb_result else None,
            "period_rows": int(len(close)),
        }
    except Exception as exc:
        return {
            "ticker": normalized,
            "error": f"{type(exc).__name__}: {exc}",
        }


@mcp.tool()
def get_stock_data(ticker: str, period: str = "3mo") -> dict[str, Any]:
    """Fetch historical OHLCV via Yahoo Finance and compute SMA, MACD, Bollinger Bands.

    Use for quantitative/technical analysis. Supports US equities and crypto
    pairs (e.g. NVDA, AAPL, BTC-USD). Returns last-bar snapshot with indicators.

    Args:
        ticker: Symbol to query (e.g. NVDA, AAPL, BTC-USD).
        period: History period, default 3mo (e.g. 1mo, 6mo, 1y).

    Returns:
        Dict with ticker, last_close, sma_20, macd_line, macd_signal,
        macd_histogram, bb_middle, bb_upper, bb_lower, period_rows.
        May include error field if data cannot be loaded.
    """
    return _get_stock_data_impl(ticker, period)


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    host = os.environ.get("MCP_MARKET_DATA_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_MARKET_DATA_PORT", "8000"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
