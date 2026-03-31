import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from fastapi import APIRouter

from ..models.schemas import StockQuote, StockQuotesResponse

logger = logging.getLogger(__name__)
router = APIRouter()

MAGNIFICENT_SEVEN = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "NVDA": "NVIDIA Corporation",
    "META": "Meta Platforms Inc.",
    "TSLA": "Tesla Inc.",
}

# Quote cache (symbol -> (quote, timestamp))
_QUOTE_CACHE: Dict[str, Tuple[StockQuote, datetime]] = {}
QUOTE_CACHE_TTL = 60  # seconds - increased to reduce Yahoo Finance API calls


async def _fetch_single_quote(symbol: str) -> StockQuote:
    """Fetch quote for a single symbol, returning error field on failure."""
    import os

    from app.mcp_client.finance_client import _call_get_us_stock_quote_async

    # Check cache first
    if symbol in _QUOTE_CACHE:
        cached_quote, cached_time = _QUOTE_CACHE[symbol]
        if datetime.now() - cached_time < timedelta(seconds=QUOTE_CACHE_TTL):
            logger.debug(f"Returning cached quote for {symbol}")
            return cached_quote

    url = os.environ.get("MCP_MARKET_DATA_URL", "http://127.0.0.1:8000/mcp")
    name = MAGNIFICENT_SEVEN.get(symbol, symbol)

    try:
        data = await _call_get_us_stock_quote_async(symbol, url)
        # Set logo path if available
        logo_path = f"/logos/{symbol}.png" if symbol in MAGNIFICENT_SEVEN else None
        quote = StockQuote(
            symbol=symbol,
            name=name,
            price=data.get("price"),
            change=data.get("change"),
            change_percent=data.get("change_percent"),
            logo=logo_path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        # Cache the successful result
        _QUOTE_CACHE[symbol] = (quote, datetime.now())
        return quote
    except Exception as exc:
        logger.warning(f"Failed to fetch quote for {symbol}: {exc}")
        # Set logo path even for error quotes
        logo_path = f"/logos/{symbol}.png" if symbol in MAGNIFICENT_SEVEN else None
        error_quote = StockQuote(symbol=symbol, name=name, logo=logo_path, error=str(exc))
        # Don't cache errors
        return error_quote


@router.get("/stocks/quotes", response_model=StockQuotesResponse)
async def get_stock_quotes(symbols: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA"):
    """Fetch real-time quotes for a comma-separated list of symbols."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    quotes = await asyncio.gather(*[_fetch_single_quote(s) for s in symbol_list])

    return StockQuotesResponse(quotes=list(quotes))
