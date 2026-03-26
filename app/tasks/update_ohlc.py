"""Scheduled task to update OHLC data daily."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.database import update_metadata, upsert_ohlc
from app.mcp_client.finance_client import call_get_stock_history

logger = logging.getLogger(__name__)

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']


async def update_daily_ohlc(ctx: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Update all stocks with latest data for scheduler or ARQ usage."""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    start_date = yesterday.isoformat()
    end_date = today.isoformat()

    logger.info(f"Starting daily OHLC update for {start_date} to {end_date}")

    success_count = 0
    total_records = 0

    for symbol in SYMBOLS:
        try:
            data = await asyncio.to_thread(call_get_stock_history, symbol, start_date, end_date)
            if data:
                await asyncio.to_thread(upsert_ohlc, symbol, data)
                await asyncio.to_thread(update_metadata, symbol, start_date, end_date)
                total_records += len(data)
                success_count += 1
                logger.info(f"✓ Updated {symbol}: {len(data)} records")

                if ctx and ctx.get("redis"):
                    cache_key = f"cache:ohlc:{symbol}:latest"
                    await ctx["redis"].set(
                        cache_key,
                        str(len(data)).encode("utf-8"),
                        ex=3600,
                    )
            else:
                logger.warning(f"✗ No data returned for {symbol}")
        except Exception as e:
            logger.error(f"✗ Failed to update {symbol}: {e}")

    logger.info(f"Daily update complete: {success_count}/{len(SYMBOLS)} stocks, {total_records} records")
    return {
        "success": success_count,
        "failed": len(SYMBOLS) - success_count,
        "total_records": total_records,
    }
