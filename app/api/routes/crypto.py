"""Crypto API routes for market data."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

from app.okx import get_okx_client
from app.okx.exceptions import (
    OKXError,
    OKXAuthError,
    OKXRateLimitError
)
from app.database.crypto_ohlc import get_crypto_ohlc
from app.database.ohlc_aggregation import aggregate_ohlc

logger = logging.getLogger(__name__)
router = APIRouter()

# Crypto name mapping
CRYPTO_NAMES = {
    'BTC-USDT': 'Bitcoin',
    'ETH-USDT': 'Ethereum'
}


class CryptoQuote(BaseModel):
    """Crypto quote model."""
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTC-USDT)")
    name: str = Field(..., description="Crypto name (e.g., Bitcoin)")
    price: float = Field(..., description="Current price")
    change: float = Field(..., description="24h price change amount")
    changePercent: float = Field(..., description="24h price change percentage")
    volume24h: float = Field(..., description="24h trading volume")
    high24h: float = Field(..., description="24h highest price")
    low24h: float = Field(..., description="24h lowest price")


class CryptoQuotesResponse(BaseModel):
    """Crypto quotes response model."""
    quotes: List[CryptoQuote] = Field(..., description="List of crypto quotes")


class OHLCRecord(BaseModel):
    """OHLC record model."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCResponse(BaseModel):
    """OHLC response model."""
    symbol: str
    data: List[OHLCRecord]


@router.get("/quotes", response_model=CryptoQuotesResponse)
async def get_crypto_quotes(
    symbols: str = Query(..., description="Comma-separated list of symbols (e.g., BTC-USDT,ETH-USDT)")
) -> CryptoQuotesResponse:
    """Get crypto quotes for specified symbols.

    Args:
        symbols: Comma-separated list of trading pair symbols

    Returns:
        CryptoQuotesResponse with list of quotes

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors, 500 for unexpected errors
    """
    try:
        logger.info(f"Getting crypto quotes for symbols: {symbols}")

        # Parse symbols
        symbol_list = [s.strip() for s in symbols.split(',')]

        # Get OKX client (demo mode)
        client = get_okx_client('demo')

        # Fetch ticker data for each symbol
        quotes = []
        for symbol in symbol_list:
            try:
                ticker = await client.get_ticker(symbol)

                # Calculate daily change (based on UTC+8 00:00 open price)
                # sodUtc8 = Start of Day UTC+8 (Beijing time 00:00)
                last_price = float(ticker.get('last', 0))
                open_today = float(ticker.get('sodUtc8', 0))

                # Fallback to 24h open if sodUtc8 not available
                if open_today == 0:
                    open_today = float(ticker.get('open24h', 0))

                change_amount = last_price - open_today
                change_pct = 0.0
                if open_today > 0:
                    change_pct = (change_amount / open_today) * 100

                # Get crypto name
                name = CRYPTO_NAMES.get(symbol, symbol)

                quote = CryptoQuote(
                    symbol=symbol,
                    name=name,
                    price=last_price,
                    change=change_amount,
                    changePercent=change_pct,
                    volume24h=float(ticker.get('vol24h', 0)),
                    high24h=float(ticker.get('high24h', 0)),
                    low24h=float(ticker.get('low24h', 0))
                )
                quotes.append(quote)

            except OKXError as e:
                logger.error(f"Error fetching ticker for {symbol}: {e}")
                raise

        logger.info(f"Successfully retrieved {len(quotes)} crypto quotes")
        return CryptoQuotesResponse(quotes=quotes)

    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{symbol}/ohlc", response_model=OHLCResponse)
def get_crypto_ohlc_endpoint(
    symbol: str,
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("15m", description="Time interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
):
    """Get OHLC data for a crypto symbol.

    Args:
        symbol: Crypto symbol (e.g., BTC-USDT)
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        interval: Time interval

    Returns:
        OHLCResponse with OHLC data
    """
    # Database uses symbol with hyphen (BTC-USDT)
    db_symbol = symbol

    # Map interval to source bar and determine if aggregation is needed
    # Database has: 1m (1-minute) and 1d (1-day)
    interval_to_source = {
        '1m': ('1m', False),
        '5m': ('1m', True),
        '15m': ('1m', True),
        '30m': ('1m', True),
        '1h': ('1m', True),
        '4h': ('1m', True),
        '1d': ('1d', False),
        'day': ('1d', False),
        '1w': ('1d', True),
        'week': ('1d', True),
        '1M': ('1d', True),  # Monthly bars
        'month': ('1d', True),
    }

    source_info = interval_to_source.get(interval)
    if not source_info:
        valid_intervals = list(interval_to_source.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Must be one of: {', '.join(valid_intervals)}"
        )

    source_bar, needs_aggregation = source_info

    # Set default date ranges
    if not end:
        end = datetime.now().date().isoformat()
    if not start:
        if source_bar == '1m':
            # For minute data, default to 7 days
            start = (datetime.now().date() - timedelta(days=7)).isoformat()
        else:
            # For daily data, default to 365 days
            start = (datetime.now().date() - timedelta(days=365)).isoformat()

    # Validate date range for minute data to prevent excessive queries
    if source_bar == '1m':
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        days_diff = (end_date - start_date).days

        # Limit minute data queries to 1 year (365 days)
        if days_diff > 365:
            raise HTTPException(
                status_code=400,
                detail=f"Date range too large for minute data. Maximum 365 days allowed, requested {days_diff} days."
            )

    # Query database
    try:
        data = get_crypto_ohlc(db_symbol, source_bar, start, end)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLC data found for {symbol}"
            )

        # Aggregate if needed
        if needs_aggregation:
            data = aggregate_ohlc(data, interval)
            if not data:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data available after aggregation for {symbol}"
                )

        # Transform to OHLCRecord list
        records = [
            OHLCRecord(
                date=record['date'],
                open=record['open'],
                high=record['high'],
                low=record['low'],
                close=record['close'],
                volume=record['volume']
            )
            for record in data
        ]

        return OHLCResponse(symbol=symbol, data=records)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch crypto OHLC for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Database error")
