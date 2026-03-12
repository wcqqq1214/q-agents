"""MCP server exposing Yahoo Finance stock quote via MCP tools."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import yfinance as yf
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("yfinance-server", json_response=True)


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

        if fast_info is not None:
            if hasattr(fast_info, "currency"):
                quote["currency"] = getattr(fast_info, "currency")
            elif isinstance(fast_info, dict):
                quote["currency"] = fast_info.get("currency")

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
        previous_close, open, day_high, day_low, volume, timestamp.
        May include an error field if the quote could not be retrieved.
    """
    return _fetch_quote_impl(ticker)


def main() -> None:
    """Run the MCP server with streamable HTTP transport."""
    import uvicorn

    host = os.environ.get("MCP_YFINANCE_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_YFINANCE_PORT", "8000"))
    app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
