"""OHLC data API endpoints."""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import get_metadata, get_ohlc_aggregated
from app.services.market_calendar import is_nyse_trading_day
from app.services.stock_updater import ensure_market_day_quote_row

logger = logging.getLogger(__name__)
router = APIRouter()
US_EASTERN = ZoneInfo("America/New_York")
FALLBACK_LOOKBACK_DAYS = 5


class OHLCRecord(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float  # Changed from int to float to handle database values


class OHLCResponse(BaseModel):
    symbol: str
    data: List[OHLCRecord]


class DataStatusResponse(BaseModel):
    symbol: str
    last_update: Optional[str]
    data_start: Optional[str]
    data_end: Optional[str]
    total_records: int


def _current_market_date(now: datetime | None = None) -> date:
    """Return the current market date in America/New_York."""
    current = now or datetime.now(US_EASTERN)
    if current.tzinfo is None:
        current = current.replace(tzinfo=US_EASTERN)
    else:
        current = current.astimezone(US_EASTERN)
    return current.date()


def _parse_record_date(value: str) -> date:
    """Parse an OHLC record date string into a date."""
    return datetime.fromisoformat(value).date()


def _get_latest_persisted_stock_date(symbol: str, start_date: date, end_date: date) -> date | None:
    """Return the latest persisted raw daily stock date in the requested window."""
    from app.database import get_ohlc

    rows = get_ohlc(symbol, start_date.isoformat(), end_date.isoformat())
    if not rows:
        return None
    return _parse_record_date(str(rows[-1]["date"]))


def _refresh_stock_rows_if_stale(
    symbol: str,
    start_date: date,
    end_date: date,
    interval: str,
) -> bool:
    """Backfill latest stock rows via MCP when the DB lags behind the market date."""
    if "-" in symbol:
        return False

    market_date = _current_market_date()
    if interval not in {"day", "week", "month", "year"}:
        return False
    if end_date < market_date:
        return False
    if not is_nyse_trading_day(market_date):
        return False

    lookback_start = max(start_date, market_date - timedelta(days=FALLBACK_LOOKBACK_DAYS))
    latest_persisted_date = _get_latest_persisted_stock_date(symbol, lookback_start, end_date)
    if latest_persisted_date is not None and latest_persisted_date >= market_date:
        return False

    fetch_start_date = lookback_start
    if latest_persisted_date is not None:
        fetch_start_date = max(start_date, latest_persisted_date - timedelta(days=1))

    from app.database import update_metadata, upsert_ohlc_overwrite
    from app.mcp_client.finance_client import call_get_stock_history

    try:
        fresh_rows = call_get_stock_history(
            symbol.upper(),
            fetch_start_date.isoformat(),
            market_date.isoformat(),
        )
        fresh_rows = ensure_market_day_quote_row(symbol.upper(), fresh_rows, market_date)
        if not fresh_rows:
            return False

        fresh_dates = [
            _parse_record_date(str(row["date"]))
            for row in fresh_rows
            if isinstance(row, dict) and row.get("date")
        ]
        if not fresh_dates:
            return False
        if latest_persisted_date is not None and max(fresh_dates) <= latest_persisted_date:
            return False

        upsert_ohlc_overwrite(symbol.upper(), fresh_rows)
        dates = [
            str(row["date"]) for row in fresh_rows if isinstance(row, dict) and row.get("date")
        ]
        if dates:
            update_metadata(symbol.upper(), min(dates), max(dates))
        return True
    except Exception as exc:
        logger.warning("Failed to refresh stale stock OHLC rows for %s: %s", symbol, exc)
        return False


def get_stock_ohlc_from_db(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    interval: str = "day",
) -> OHLCResponse:
    """Get OHLC data for a stock symbol from database.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        interval: Time interval (day, week, month, year)

    Returns:
        OHLCResponse with stock OHLC data
    """
    # Validate interval
    valid_intervals = ["day", "week", "month", "year"]
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Must be one of: {', '.join(valid_intervals)}",
        )

    # Default to 5 years if not specified
    market_date = _current_market_date()
    if not end:
        end = market_date.isoformat()
    if not start:
        start = (market_date - timedelta(days=5 * 365)).isoformat()

    # Validate date range
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start date must be before end date")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}") from e

    # Query database with aggregation
    try:
        data = get_ohlc_aggregated(symbol, start, end, interval)
        if _refresh_stock_rows_if_stale(symbol, start_date, end_date, interval):
            data = get_ohlc_aggregated(symbol, start, end, interval)
        if not data:
            raise HTTPException(status_code=404, detail=f"No OHLC data found for {symbol}")

        return OHLCResponse(symbol=symbol.upper(), data=[OHLCRecord(**record) for record in data])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to fetch OHLC for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Database error") from e


@router.get("/{symbol}/ohlc", response_model=OHLCResponse)
def get_stock_ohlc(
    symbol: str,
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("day", description="Time granularity: day, week, month, year"),
):
    """Get OHLC data for a stock symbol with optional time aggregation."""
    return get_stock_ohlc_from_db(symbol, start, end, interval)


@router.get("/{symbol}/data-status", response_model=DataStatusResponse)
def get_data_status(symbol: str):
    """Get data status for a stock symbol."""
    metadata = get_metadata(symbol)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    # Count total records
    from app.database import get_conn

    conn = get_conn()
    try:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM ohlc WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return DataStatusResponse(
        symbol=symbol.upper(),
        last_update=metadata.get("last_update"),
        data_start=metadata.get("data_start"),
        data_end=metadata.get("data_end"),
        total_records=count,
    )
