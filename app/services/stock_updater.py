"""Stock data updater with intraday support."""

import asyncio
import os
import logging
from typing import Dict, List
from pathlib import Path
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
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
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
    if symbols_count == 1:
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


async def update_stocks_intraday() -> None:
    """Async wrapper for the intraday stock update."""
    try:
        await asyncio.to_thread(update_stocks_intraday_sync)
    except Exception as exc:
        logger.error(f"Intraday update failed: {exc}", exc_info=True)
