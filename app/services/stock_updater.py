"""Stock data updater with intraday support."""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

import app.database as stock_db
from app.services.trading_hours import should_update_stocks

logger = logging.getLogger(__name__)

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
UTC = ZoneInfo("UTC")
US_EASTERN = ZoneInfo("America/New_York")

# yfinance reads proxy/cache settings from process environment. The default
# sandbox profile points to a local proxy and a non-writable cache directory,
# so we normalize those settings here to make the updater usable by default.
for _proxy_var in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(_proxy_var, None)

_YFINANCE_CACHE_DIR = Path("/tmp/codex-yfinance-cache")
_YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(_YFINANCE_CACHE_DIR))


def normalize_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a yfinance DataFrame index to naive UTC timestamps."""
    if df.empty:
        return df

    normalized = df.copy()
    if normalized.index.tz is None:
        normalized.index = normalized.index.tz_localize(US_EASTERN).tz_convert(UTC)
    else:
        normalized.index = normalized.index.tz_convert(UTC)

    normalized.index = normalized.index.tz_localize(None)
    return normalized


def _extract_symbol_frame(data: pd.DataFrame, symbol: str, symbols_count: int) -> pd.DataFrame:
    """Extract data for a single symbol from a yfinance download result."""
    if symbols_count == 1:
        if isinstance(data.columns, pd.MultiIndex):
            if symbol in data.columns.get_level_values(1):
                return data.droplevel(1, axis=1)
        return data

    if isinstance(data.columns, pd.MultiIndex):
        if symbol in data.columns.get_level_values(0):
            return data[symbol]
        if symbol in data.columns.get_level_values(-1):
            return data.xs(symbol, axis=1, level=-1)

    return data


def fetch_recent_ohlc(symbols: List[str], days: int = 5) -> Dict[str, List[Dict]]:
    """Fetch recent daily OHLC data for the requested symbols."""
    logger.info(f"Fetching {days}-day data for {len(symbols)} symbols...")

    try:
        data = yf.download(
            tickers=symbols,
            period=f"{days}d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
        )

        result: Dict[str, List[Dict]] = {}
        for symbol in symbols:
            try:
                df = _extract_symbol_frame(data, symbol, len(symbols))
                if df.empty:
                    logger.warning(f"No data returned for {symbol}")
                    continue

                df = normalize_timezone(df)

                records: List[Dict] = []
                for date, row in df.iterrows():
                    if pd.isna(row.get("Close")) or pd.isna(row.get("Open")):
                        continue

                    records.append(
                        {
                            "date": date.strftime("%Y-%m-%d"),
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": int(row["Volume"]),
                        }
                    )

                result[symbol] = records
                if records:
                    latest = records[-1]
                    logger.info(
                        f"✓ {symbol}: {len(records)} records | "
                        f"Latest: {latest['date']} Close=${latest['close']:.2f}"
                    )
            except Exception as exc:
                logger.error(f"Failed to process {symbol}: {exc}")
                continue

        return result
    except Exception as exc:
        logger.error(f"Failed to fetch data: {exc}")
        return {}


def get_current_market_date(now: datetime | None = None) -> date:
    """Return the current US market date in America/New_York."""
    current = now or datetime.now(US_EASTERN)
    if current.tzinfo is None:
        current = current.replace(tzinfo=US_EASTERN)
    else:
        current = current.astimezone(US_EASTERN)
    return current.date()


def _parse_row_date(value: str) -> date:
    """Parse a stock OHLC row date into a ``date`` instance."""
    return datetime.fromisoformat(value).date()


def _build_market_day_row_from_quote(
    market_date: date, quote: Dict[str, float | int | None]
) -> Dict | None:
    """Build a synthetic daily OHLC row for the current market day from a quote payload."""
    close_price = quote.get("price")
    if close_price is None:
        return None

    open_price = quote.get("open")
    if open_price is None:
        open_price = quote.get("previous_close", close_price)

    high_price = quote.get("day_high")
    low_price = quote.get("day_low")

    open_value = float(open_price) if open_price is not None else float(close_price)
    close_value = float(close_price)
    high_value = float(high_price) if high_price is not None else max(open_value, close_value)
    low_value = float(low_price) if low_price is not None else min(open_value, close_value)
    volume_value = int(quote.get("volume") or 0)

    return {
        "date": market_date.isoformat(),
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume_value,
    }


def ensure_market_day_quote_row(symbol: str, records: List[Dict], market_date: date) -> List[Dict]:
    """Append a quote-derived market-day row when history data still lags behind ``market_date``."""
    latest_record_date = max((_parse_row_date(str(row["date"])) for row in records), default=None)
    if latest_record_date is not None and latest_record_date >= market_date:
        return records

    from app.mcp_client.finance_client import call_get_us_stock_quote

    quote = call_get_us_stock_quote(symbol)
    synthetic_row = _build_market_day_row_from_quote(market_date, quote)
    if synthetic_row is None:
        return records

    filtered_rows = [row for row in records if str(row.get("date")) != synthetic_row["date"]]
    filtered_rows.append(synthetic_row)
    filtered_rows.sort(key=lambda row: str(row["date"]))
    return filtered_rows


def fetch_recent_ohlc_from_mcp(
    symbols: List[str],
    days: int = 5,
    market_date: date | None = None,
) -> Dict[str, List[Dict]]:
    """Fetch recent daily OHLC rows through the MCP stock-history client."""
    from app.mcp_client.finance_client import call_get_stock_history

    end_date = market_date or get_current_market_date()
    start_date = end_date - timedelta(days=days)
    result: Dict[str, List[Dict]] = {}

    for symbol in symbols:
        try:
            data = call_get_stock_history(symbol, start_date.isoformat(), end_date.isoformat())
            records: List[Dict] = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                if not row.get("date"):
                    continue
                records.append(
                    {
                        "date": str(row["date"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )

            records = ensure_market_day_quote_row(symbol, records, end_date)

            if not records:
                logger.warning(f"No MCP stock history returned for {symbol}")
                continue

            result[symbol] = records
            latest = records[-1]
            logger.info(
                f"✓ {symbol}: {len(records)} MCP records | "
                f"Latest: {latest['date']} Close=${latest['close']:.2f}"
            )
        except Exception as exc:
            logger.error(f"Failed to fetch MCP history for {symbol}: {exc}")

    return result


async def _fetch_with_rate_limit(
    symbols: List[str], days: int, delay: float
) -> Dict[str, List[Dict]]:
    """Fetch stock data with rate limiting to avoid Yahoo Finance ban.

    Args:
        symbols: List of stock symbols
        days: Number of days to fetch
        delay: Delay between requests in seconds

    Returns:
        Dict mapping symbol to list of OHLC records
    """
    result = {}

    for i, symbol in enumerate(symbols):
        try:
            # Add delay between requests (except first one)
            if i > 0:
                await asyncio.sleep(delay)

            # Fetch data for single symbol
            data = await asyncio.to_thread(fetch_recent_ohlc, [symbol], days)

            if symbol in data:
                result[symbol] = data[symbol]
                logger.debug(f"Fetched {len(data[symbol])} records for {symbol}")
            else:
                logger.warning(f"No data returned for {symbol}")

        except Exception as exc:
            logger.error(f"Failed to fetch {symbol}: {exc}")
            continue

    return result


async def catchup_historical_stocks(days: int) -> dict:
    """Catch up missing historical stock data on startup.

    Args:
        days: Maximum number of days to look back

    Returns:
        Statistics dict with keys:
            - symbols_updated: int
            - records_added: int
            - date_range: tuple (start_date, end_date) or None
            - errors: list of error messages
    """
    from datetime import date, datetime

    from app.config_manager import get_stock_catchup_config
    from app.database.ohlc import get_metadata, update_metadata, upsert_ohlc_overwrite

    # Validate AAPL is in SYMBOLS list (used as sentinel)
    if "AAPL" not in SYMBOLS:
        error_msg = "AAPL sentinel symbol not in SYMBOLS list"
        logger.error(error_msg)
        return {
            "symbols_updated": 0,
            "records_added": 0,
            "date_range": None,
            "errors": [error_msg],
        }

    logger.info(f"Starting stock catch-up (max {days} days)...")

    # Check last update date from metadata
    # Use AAPL as sentinel - assumes all symbols are updated together
    # Trade-off: Fast startup vs. handling symbols added at different times
    metadata = get_metadata("AAPL")

    if metadata is None:
        logger.info(f"No metadata found, fetching last {days} days")
        fetch_days = days
    else:
        last_date = datetime.fromisoformat(metadata["data_end"]).date()
        today = date.today()
        gap_days = (today - last_date).days

        if gap_days <= 1:
            logger.info(f"Stock data is up to date (last: {last_date})")
            return {
                "symbols_updated": 0,
                "records_added": 0,
                "date_range": None,
                "errors": [],
            }

        fetch_days = min(gap_days, days)
        logger.info(f"Gap detected: {gap_days} days, fetching last {fetch_days} days")

    # Fetch with rate limiting
    config = get_stock_catchup_config()
    data_by_symbol = await _fetch_with_rate_limit(SYMBOLS, fetch_days, config["rate_limit_delay"])

    # Save to database
    stats = {"symbols_updated": 0, "records_added": 0, "date_range": None, "errors": []}

    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                dates = [r["date"] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                stats["symbols_updated"] += 1
                stats["records_added"] += len(records)

                if stats["date_range"] is None:
                    stats["date_range"] = (min(dates), max(dates))

                logger.info(f"✓ {symbol}: {len(records)} records | Latest: {records[-1]['date']}")
        except Exception as exc:
            error_msg = f"{symbol}: {exc}"
            stats["errors"].append(error_msg)
            logger.error(f"Failed to save {symbol}: {exc}")

    logger.info(f"✓ Catch-up completed: {stats['symbols_updated']}/{len(SYMBOLS)} symbols updated")
    return stats


def update_stocks_intraday_sync() -> None:
    """Blocking intraday update routine meant to run in a worker thread."""
    if not should_update_stocks():
        return

    logger.info("=" * 60)
    logger.info("Starting intraday stock update")
    logger.info("=" * 60)

    data_by_symbol = fetch_recent_ohlc_from_mcp(SYMBOLS, days=5)
    if not data_by_symbol:
        logger.error("No data fetched, aborting update")
        return

    success_count = 0
    today_prices: List[str] = []

    for symbol, records in data_by_symbol.items():
        try:
            if records:
                stock_db.upsert_ohlc_overwrite(symbol, records)
                dates = [r["date"] for r in records]
                stock_db.update_metadata(symbol, min(dates), max(dates))
                latest = records[-1]
                today_prices.append(f"{symbol}=${latest['close']:.2f}")
                success_count += 1
        except Exception as exc:
            logger.error(f"Failed to upsert {symbol}: {exc}")

    logger.info("=" * 60)
    logger.info(f"Update complete: {success_count}/{len(SYMBOLS)} symbols updated")
    if today_prices:
        logger.info(f"Latest prices: {' | '.join(today_prices)}")
    logger.info("=" * 60)


async def update_stocks_intraday(force: bool = False) -> None:
    """Async wrapper for the intraday stock update.

    Args:
        force: If True, bypass trading hours check and update anyway
    """
    if not force and not should_update_stocks():
        logger.info("Skipping update: outside trading hours or holiday")
        return

    try:
        await asyncio.to_thread(update_stocks_intraday_sync)
    except Exception as exc:
        logger.error(f"Intraday update failed: {exc}", exc_info=True)
