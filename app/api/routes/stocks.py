from fastapi import APIRouter
from datetime import datetime, timezone
import asyncio
import logging

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


async def _fetch_single_quote(symbol: str) -> StockQuote:
    """Fetch quote for a single symbol, returning error field on failure."""
    import os
    from app.mcp_client.finance_client import _call_get_us_stock_quote_async
    from app.polygon.client import fetch_ticker_details

    url = os.environ.get("MCP_MARKET_DATA_URL", "http://127.0.0.1:8000/mcp")
    name = MAGNIFICENT_SEVEN.get(symbol, symbol)

    try:
        data = await _call_get_us_stock_quote_async(symbol, url)
        logo = await asyncio.to_thread(fetch_ticker_details, symbol)
        return StockQuote(
            symbol=symbol,
            name=name,
            price=data.get("price"),
            change=data.get("change"),
            change_percent=data.get("change_percent"),
            logo=logo,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.warning(f"Failed to fetch quote for {symbol}: {exc}")
        return StockQuote(symbol=symbol, name=name, error=str(exc))


@router.get("/stocks/quotes", response_model=StockQuotesResponse)
async def get_stock_quotes(symbols: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA"):
    """Fetch real-time quotes for a comma-separated list of symbols."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    quotes = await asyncio.gather(*[_fetch_single_quote(s) for s in symbol_list])
    return StockQuotesResponse(quotes=list(quotes))
