"""OKX API routes for account management."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import logging

from app.okx import get_okx_client
from app.okx.exceptions import (
    OKXError,
    OKXAuthError,
    OKXRateLimitError,
    OKXConfigError
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/okx/account/balance")
async def get_account_balance(
    mode: str = Query(default="demo", description="Trading mode: demo or live"),
    currency: Optional[str] = Query(default=None, description="Currency code (e.g., USDT, BTC)")
) -> Dict[str, Any]:
    """Get account balance.

    Args:
        mode: Trading mode (demo or live)
        currency: Optional currency filter

    Returns:
        Dictionary with mode and balances list

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(f"Getting account balance - mode: {mode}, currency: {currency}")
        client = get_okx_client(mode)
        balances = await client.get_account_balance(currency=currency)
        logger.info(f"Successfully retrieved {len(balances)} balance(s)")
        return {"mode": mode, "balances": balances}
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/okx/account/positions")
async def get_account_positions(
    mode: str = Query(default="demo", description="Trading mode: demo or live"),
    inst_type: Optional[str] = Query(default=None, description="Instrument type (e.g., SWAP, FUTURES, SPOT)")
) -> Dict[str, Any]:
    """Get account positions.

    Args:
        mode: Trading mode (demo or live)
        inst_type: Optional instrument type filter

    Returns:
        Dictionary with mode and positions list

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(f"Getting account positions - mode: {mode}, inst_type: {inst_type}")
        client = get_okx_client(mode)
        positions = await client.get_positions(inst_type=inst_type)
        logger.info(f"Successfully retrieved {len(positions)} position(s)")
        return {"mode": mode, "positions": positions}
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
