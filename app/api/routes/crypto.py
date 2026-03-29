"""Crypto API routes for market data."""

import logging
from typing import List

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.services.hot_cache import get_hot_cache

logger = logging.getLogger(__name__)
router = APIRouter()

# Crypto name mapping
CRYPTO_NAMES = {"BTC-USDT": "Bitcoin", "ETH-USDT": "Ethereum"}


class CryptoQuote(BaseModel):
    """Crypto quote model."""

    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="Trading pair symbol (e.g., BTC-USDT)")
    name: str = Field(..., description="Crypto name (e.g., Bitcoin)")
    price: float = Field(..., description="Current price")
    change: float = Field(..., description="24h price change amount")
    change_percent: float = Field(..., alias="changePercent", description="24h price change percentage")
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
    symbols: str = Query(
        ..., description="Comma-separated list of symbols (e.g., BTC-USDT,ETH-USDT)"
    ),
) -> CryptoQuotesResponse:
    """Get crypto quotes for specified symbols from Binance hot cache.

    Args:
        symbols: Comma-separated list of trading pair symbols

    Returns:
        CryptoQuotesResponse with list of quotes

    Raises:
        HTTPException: 400 for invalid symbols or missing data, 500 for unexpected errors
    """
    try:
        logger.info(f"Getting crypto quotes for symbols: {symbols}")

        # Parse symbols
        symbol_list = [s.strip() for s in symbols.split(",")]

        # Fetch quotes from hot cache
        quotes = []
        for symbol in symbol_list:
            try:
                # Convert BTC-USDT to BTCUSDT format for hot cache
                cache_symbol = symbol.replace("-", "")

                # Get 1-minute data from hot cache
                df = get_hot_cache(cache_symbol, "1m")

                if df.empty:
                    logger.warning(f"No data in hot cache for {symbol}")
                    # Return zero values if no data
                    name = CRYPTO_NAMES.get(symbol, symbol)
                    quote = CryptoQuote(
                        symbol=symbol,
                        name=name,
                        price=0.0,
                        change=0.0,
                        change_percent=0.0,
                        volume24h=0.0,
                        high24h=0.0,
                        low24h=0.0,
                    )
                    quotes.append(quote)
                    continue

                # Get latest record (most recent 1-minute candle)
                latest = df.iloc[-1]
                last_price = float(latest["close"])

                # Calculate daily statistics from local time 00:00 today
                from datetime import datetime

                # Get local timezone (system timezone)
                local_tz = datetime.now().astimezone().tzinfo

                # Get today's 00:00 in local time
                now_local = datetime.now(local_tz)
                today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

                # Convert timestamp column to datetime for filtering
                # timestamp is in milliseconds
                df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

                # Filter data from today 00:00 onwards
                df_today = df[df["datetime"] >= today_start]

                if len(df_today) > 0:
                    open_today = float(df_today.iloc[0]["open"])
                    high_today = float(df_today["high"].max())
                    low_today = float(df_today["low"].min())
                    volume_today = float(df_today["volume"].sum())

                    change_amount = last_price - open_today
                    change_pct = (change_amount / open_today * 100) if open_today > 0 else 0.0
                else:
                    # Fallback if no data from today (e.g., just after midnight)
                    open_today = last_price
                    high_today = last_price
                    low_today = last_price
                    volume_today = 0.0
                    change_amount = 0.0
                    change_pct = 0.0

                # Get crypto name
                name = CRYPTO_NAMES.get(symbol, symbol)

                quote = CryptoQuote(
                    symbol=symbol,
                    name=name,
                    price=last_price,
                    change=change_amount,
                    change_percent=change_pct,
                    volume24h=volume_today,
                    high24h=high_today,
                    low24h=low_today,
                )
                quotes.append(quote)

            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                # Continue with other symbols instead of failing completely
                continue

        if not quotes:
            raise HTTPException(status_code=400, detail="No valid quotes retrieved")

        logger.info(f"Successfully retrieved {len(quotes)} crypto quotes from hot cache")
        return CryptoQuotesResponse(quotes=quotes)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") from e
