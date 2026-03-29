"""Crypto K-lines API endpoint."""

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.database.crypto_ohlc import get_crypto_ohlc
from app.database.ohlc_aggregation import aggregate_ohlc
from app.services.hot_cache import get_hot_cache

router = APIRouter()


@router.get("/crypto/klines")
async def get_crypto_klines(
    symbol: str = Query(..., description="Trading pair symbol (e.g., BTCUSDT)"),
    interval: str = Query(..., description="K-line interval: 15m, 1h, 4h, 1d, 1w, 1M"),
    start: Optional[str] = Query(None, description="Start date in ISO format"),
    end: Optional[str] = Query(None, description="End date in ISO format"),
) -> List[dict]:
    """
    Get crypto K-line data by merging cold (database) and hot (cache) data.

    This endpoint implements the Lambda architecture pattern:
    1. Fetch historical data from cold storage (SQLite)
    2. Fetch recent data from hot cache (in-memory)
    3. Merge and deduplicate (hot data takes precedence)
    4. Aggregate to requested interval if needed
    5. Return sorted by timestamp

    Supported intervals (matching frontend):
    - 15m: 15 minutes
    - 1h: 1 hour
    - 4h: 4 hours
    - 1d: 1 day
    - 1w: 1 week
    - 1M: 1 month

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        interval: K-line interval (15m, 1h, 4h, 1d, 1w, 1M)
        start: Optional start date filter
        end: Optional end date filter

    Returns:
        List of K-line records with keys: timestamp, date, open, high, low, close, volume
    """
    # Map interval to source bar and determine if aggregation is needed
    # Only support intervals that frontend uses
    interval_to_source = {
        "15m": ("1m", True),  # 15 Min button
        "1h": ("1m", True),  # 1 Hour button
        "4h": ("1m", True),  # 4 Hour button
        "1d": ("1d", False),  # 1 Day button
        "1w": ("1d", True),  # 1 Week button
        "1M": ("1d", True),  # 1 Month button
    }

    source_info = interval_to_source.get(interval)
    if not source_info:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Supported: {', '.join(interval_to_source.keys())}",
        )

    source_bar, needs_aggregation = source_info

    # Convert symbol format: BTCUSDT -> BTC-USDT for database
    if symbol.endswith("USDT") and "-" not in symbol:
        db_symbol = f"{symbol[:-4]}-USDT"
    else:
        db_symbol = symbol

    # Fetch cold data from database
    cold_data = get_crypto_ohlc(symbol=db_symbol, bar=source_bar, start=start, end=end)

    # Fetch hot data from cache
    hot_df = get_hot_cache(symbol, source_bar)

    # Convert cold data to DataFrame
    if cold_data:
        cold_df = pd.DataFrame(cold_data)
        # Remove 'symbol' and 'bar' columns to match hot data format
        cold_df = cold_df[["timestamp", "date", "open", "high", "low", "close", "volume"]]
    else:
        cold_df = pd.DataFrame(
            columns=["timestamp", "date", "open", "high", "low", "close", "volume"]
        )

    # Merge cold and hot data
    # Only use hot cache for data at or after the cold DB's latest timestamp.
    # This prevents stale/incomplete hot cache from overriding complete DB history.
    if not hot_df.empty and not cold_df.empty:
        cold_max_ts = cold_df["timestamp"].max()
        hot_df = hot_df[hot_df["timestamp"] >= cold_max_ts]

    if not hot_df.empty:
        merged_df = pd.concat([cold_df, hot_df], ignore_index=True)
    else:
        merged_df = cold_df

    # Deduplicate by timestamp (keep last, which prioritizes hot data for the overlap point)
    if not merged_df.empty:
        merged_df = merged_df.drop_duplicates(subset=["timestamp"], keep="last")
        merged_df = merged_df.sort_values("timestamp")

    # Convert to list of dicts
    result = merged_df.to_dict("records")

    # Aggregate if needed
    if needs_aggregation and result:
        result = aggregate_ohlc(result, interval)

    return result
