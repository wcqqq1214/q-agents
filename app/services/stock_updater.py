"""Stock data updater with intraday support."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.database.ohlc import update_metadata, upsert_ohlc_overwrite
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

    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=5)
    if not data_by_symbol:
        logger.error("No data fetched, aborting update")
        return

    success_count = 0
    today_prices: List[str] = []

    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                dates = [r["date"] for r in records]
                update_metadata(symbol, min(dates), max(dates))
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
