"""Realtime agent for hot cache warmup and updates."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.database.crypto_ohlc import get_max_timestamp
from app.services.binance_client import (
    fetch_binance_klines,
    fetch_klines_with_pagination,
)
from app.services.hot_cache import append_to_hot_cache, cleanup_hot_cache

logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "1d"]
WARMUP_HOURS = 48
UPDATE_HOURS = 1


def _convert_to_db_symbol(binance_symbol: str) -> str:
    """Convert Binance symbol format to database format.

    Args:
        binance_symbol: Symbol in Binance format (e.g., 'BTCUSDT')

    Returns:
        Symbol in database format (e.g., 'BTC-USDT')
    """
    # Simple conversion: insert hyphen before 'USDT'
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}-USDT"
    return binance_symbol


async def _warmup_single(
    symbol: str, interval: str, now: datetime, end_time: int, max_gap_hours: int
) -> None:
    """
    Warmup hot cache for a single symbol and interval.

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Time interval (e.g., '1m', '1d')
        now: Current datetime
        end_time: End timestamp in milliseconds
        max_gap_hours: Maximum gap hours to fetch

    Raises:
        Exception: Any error during warmup (will be caught by gather)
    """
    logger.info(f"Warming up {symbol} {interval}...")

    # Convert symbol format for database query
    db_symbol = _convert_to_db_symbol(symbol)

    # Query database for max timestamp
    max_timestamp = get_max_timestamp(db_symbol, interval)

    if max_timestamp is None:
        # Case 1: Database is empty - fetch last 48 hours
        start_time = int((now - timedelta(hours=max_gap_hours)).timestamp() * 1000)
        logger.info(f"Database empty for {symbol} {interval}, fetching last {max_gap_hours} hours")

        klines = await fetch_binance_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=1000,
        )
    else:
        # Calculate gap in hours
        gap_ms = end_time - max_timestamp
        gap_hours = gap_ms / (1000 * 60 * 60)

        # Use small gap path if gap is within max_gap_hours (with small tolerance for floating point)
        if gap_hours < max_gap_hours + 0.01:
            # Case 2: Small gap - fetch from max_timestamp + 1 to now
            start_time = max_timestamp + 1
            logger.info(f"Gap of {gap_hours:.1f}h detected for {symbol} {interval}, filling gap")

            # Use pagination for potentially large gaps
            klines = await fetch_klines_with_pagination(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            # Case 3: Large gap - only fetch last 48 hours to avoid long startup
            start_time = int((now - timedelta(hours=max_gap_hours)).timestamp() * 1000)
            logger.info(
                f"Gap of {gap_hours:.1f}h detected for {symbol} {interval}, fetching last {max_gap_hours}h only"
            )

            klines = await fetch_binance_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                end_time=end_time,
                limit=1000,
            )

    if klines:
        append_to_hot_cache(symbol, interval, klines)
        logger.info(f"✓ Warmed up {symbol} {interval} with {len(klines)} records")
    else:
        logger.warning(f"No data returned for {symbol} {interval}")


async def warmup_hot_cache() -> None:
    """
    Warmup hot cache with parallel execution for all symbols and intervals.

    This function is called on application startup to populate the hot cache
    with recent historical data. It intelligently determines what data to fetch:

    1. If database is empty: fetch last 48 hours
    2. If gap <= 48 hours: fetch from max_timestamp + 1 to now
    3. If gap > 48 hours: only fetch last 48 hours (avoid long startup)

    Uses pagination for gaps that may exceed 1000 records.
    All symbol/interval combinations are fetched in parallel for faster startup.
    """
    logger.info("Starting parallel hot cache warmup...")

    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp() * 1000)
    max_gap_hours = WARMUP_HOURS

    # Collect all warmup tasks
    tasks = []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            task = _warmup_single(symbol, interval, now, end_time, max_gap_hours)
            tasks.append((symbol, interval, task))

    # Execute all tasks in parallel with exception handling
    logger.info(f"Launching {len(tasks)} parallel warmup tasks...")
    results = await asyncio.gather(*[task for _, _, task in tasks], return_exceptions=True)

    # Check results and log any failures
    success_count = 0
    failure_count = 0
    for (symbol, interval, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            failure_count += 1
            logger.error(f"✗ Failed to warmup {symbol} {interval}: {result}", exc_info=result)
        else:
            success_count += 1

    logger.info(
        f"Hot cache warmup completed: {success_count} succeeded, {failure_count} failed out of {len(tasks)} total"
    )


async def update_hot_cache() -> None:
    """
    Update hot cache with latest data and cleanup old data.

    This function is called periodically (e.g., every minute) to:
    1. Fetch the latest data from Binance API
    2. Append new data to hot cache
    3. Remove data older than 48 hours
    """
    logger.debug("Updating hot cache...")

    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp() * 1000)
    start_time = int((now - timedelta(hours=UPDATE_HOURS)).timestamp() * 1000)
    cutoff_time = now - timedelta(hours=WARMUP_HOURS)

    for symbol in SYMBOLS:
        for interval in INTERVALS:
            try:
                # Fetch latest data
                klines = await fetch_binance_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    limit=1000,
                )

                if klines:
                    append_to_hot_cache(symbol, interval, klines)
                    logger.debug(f"Updated {symbol} {interval} with {len(klines)} records")

                # Cleanup old data
                cleanup_hot_cache(symbol, interval, cutoff_time)

            except Exception as e:
                logger.error(f"Failed to update {symbol} {interval}: {e}", exc_info=True)

    logger.debug("Hot cache update completed")


async def update_hot_cache_loop() -> None:
    """
    Continuous loop that updates hot cache every 60 seconds.

    This function runs as a background task and periodically fetches
    the latest data from Binance API to keep the hot cache fresh.
    """
    logger.info("Starting hot cache update loop...")

    while True:
        try:
            await asyncio.sleep(60)  # Wait 60 seconds between updates
            await update_hot_cache()
        except Exception as e:
            logger.error(f"Error in hot cache update loop: {e}", exc_info=True)
            # Continue running even if one update fails
            await asyncio.sleep(60)
