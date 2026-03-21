"""Crypto API routes for market data."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import logging

from app.okx import get_okx_client
from app.okx.exceptions import (
    OKXError,
    OKXAuthError,
    OKXRateLimitError
)

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
    price: str = Field(..., description="Current price")
    open24h: str = Field(..., description="24h opening price")
    high24h: str = Field(..., description="24h highest price")
    low24h: str = Field(..., description="24h lowest price")
    volume24h: str = Field(..., description="24h trading volume")
    change24h: str = Field(..., description="24h price change percentage")


class CryptoQuotesResponse(BaseModel):
    """Crypto quotes response model."""
    quotes: List[CryptoQuote] = Field(..., description="List of crypto quotes")


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

                # Calculate 24h change percentage
                last_price = float(ticker.get('last', 0))
                open_price = float(ticker.get('open24h', 0))
                change_pct = 0.0
                if open_price > 0:
                    change_pct = ((last_price - open_price) / open_price) * 100

                # Get crypto name
                name = CRYPTO_NAMES.get(symbol, symbol)

                quote = CryptoQuote(
                    symbol=symbol,
                    name=name,
                    price=ticker.get('last', '0'),
                    open24h=ticker.get('open24h', '0'),
                    high24h=ticker.get('high24h', '0'),
                    low24h=ticker.get('low24h', '0'),
                    volume24h=ticker.get('vol24h', '0'),
                    change24h=f"{change_pct:.2f}"
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
