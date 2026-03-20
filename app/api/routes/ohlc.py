"""OHLC data API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_ohlc, get_metadata

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.get("/{symbol}/ohlc", response_model=OHLCResponse)
def get_stock_ohlc(
    symbol: str,
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get OHLC data for a stock symbol."""
    # Default to 5 years if not specified
    if not end:
        end = datetime.now().date().isoformat()
    if not start:
        start = (datetime.now().date() - timedelta(days=5*365)).isoformat()

    # Validate date range
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start date must be before end date")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    # Query database
    try:
        data = get_ohlc(symbol, start, end)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLC data found for {symbol}"
            )

        return OHLCResponse(
            symbol=symbol.upper(),
            data=[OHLCRecord(**record) for record in data]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch OHLC for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/{symbol}/data-status", response_model=DataStatusResponse)
def get_data_status(symbol: str):
    """Get data status for a stock symbol."""
    metadata = get_metadata(symbol)

    if not metadata:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol}"
        )

    # Count total records
    from app.database import get_conn
    conn = get_conn()
    try:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM ohlc WHERE symbol = ?",
            (symbol.upper(),)
        ).fetchone()['cnt']
    finally:
        conn.close()

    return DataStatusResponse(
        symbol=symbol.upper(),
        last_update=metadata.get('last_update'),
        data_start=metadata.get('data_start'),
        data_end=metadata.get('data_end'),
        total_records=count
    )
