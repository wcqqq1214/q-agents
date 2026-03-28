"""OKX API routes for account management."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.okx import get_okx_client
from app.okx.exceptions import (
    OKXAuthError,
    OKXConfigError,
    OKXError,
    OKXInsufficientBalanceError,
    OKXOrderError,
    OKXRateLimitError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class PlaceOrderRequest(BaseModel):
    """下单请求"""

    mode: str = Field(..., description="交易模式 (live/demo)")
    inst_id: str = Field(..., description="产品ID，如BTC-USDT")
    side: str = Field(..., description="订单方向 (buy/sell)")
    order_type: str = Field(..., description="订单类型 (market/limit/post_only/fok/ioc)")
    size: str = Field(..., description="委托数量")
    price: Optional[str] = Field(None, description="委托价格（限价单必填）")
    client_order_id: Optional[str] = Field(None, description="客户端订单ID")


@router.get("/okx/account/balance")
async def get_account_balance(
    mode: str = Query(default="demo", description="Trading mode: demo or live"),
    currency: Optional[str] = Query(default=None, description="Currency code (e.g., USDT, BTC)"),
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


@router.post("/okx/trade/order")
async def place_order(request: PlaceOrderRequest) -> Dict[str, Any]:
    """Place a trading order.

    Args:
        request: Order placement request

    Returns:
        Dictionary with mode, order_id, client_order_id, and status_code

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(
            f"Placing order - mode: {request.mode}, inst_id: {request.inst_id}, side: {request.side}, type: {request.order_type}"
        )
        client = get_okx_client(request.mode)
        result = await client.place_order(
            inst_id=request.inst_id,
            side=request.side,
            order_type=request.order_type,
            size=request.size,
            price=request.price,
            client_order_id=request.client_order_id,
        )
        logger.info(f"Order placed successfully - order_id: {result.get('order_id')}")
        return {
            "mode": request.mode,
            "order_id": result.get("order_id"),
            "client_order_id": result.get("client_order_id"),
            "status_code": result.get("status_code"),
        }
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXInsufficientBalanceError as e:
        logger.error(f"Insufficient balance error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/okx/trade/order/{order_id}")
async def cancel_order(
    order_id: str,
    mode: str = Query(..., description="Trading mode: demo or live"),
    inst_id: str = Query(..., description="Instrument ID (e.g., BTC-USDT)"),
    client_order_id: Optional[str] = Query(None, description="Client order ID"),
) -> Dict[str, Any]:
    """Cancel a trading order.

    Args:
        order_id: Order ID to cancel
        mode: Trading mode (demo or live)
        inst_id: Instrument ID
        client_order_id: Optional client order ID

    Returns:
        Dictionary with mode, order_id, client_order_id, and status_code

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(f"Canceling order - mode: {mode}, order_id: {order_id}, inst_id: {inst_id}")
        client = get_okx_client(mode)
        result = await client.cancel_order(
            order_id=order_id, inst_id=inst_id, client_order_id=client_order_id
        )
        logger.info(f"Order canceled successfully - order_id: {order_id}")
        return {
            "mode": mode,
            "order_id": result.get("order_id"),
            "client_order_id": result.get("client_order_id"),
            "status_code": result.get("status_code"),
        }
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXInsufficientBalanceError as e:
        logger.error(f"Insufficient balance error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/okx/trade/order/{order_id}")
async def get_order_details(
    order_id: str,
    mode: str = Query(..., description="Trading mode: demo or live"),
    inst_id: str = Query(..., description="Instrument ID (e.g., BTC-USDT)"),
    client_order_id: Optional[str] = Query(None, description="Client order ID"),
) -> Dict[str, Any]:
    """Get order details.

    Args:
        order_id: Order ID to query
        mode: Trading mode (demo or live)
        inst_id: Instrument ID
        client_order_id: Optional client order ID

    Returns:
        Dictionary with mode and order details

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(
            f"Getting order details - mode: {mode}, order_id: {order_id}, inst_id: {inst_id}"
        )
        client = get_okx_client(mode)
        order = await client.get_order_details(
            order_id=order_id, inst_id=inst_id, client_order_id=client_order_id
        )
        logger.info(f"Order details retrieved successfully - order_id: {order_id}")
        return {"mode": mode, "order": order}
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXInsufficientBalanceError as e:
        logger.error(f"Insufficient balance error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"OKX error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/okx/trade/orders/history")
async def get_order_history(
    mode: str = Query(default="demo", description="Trading mode: demo or live"),
    inst_type: str = Query(
        default="SPOT", description="Instrument type (e.g., SPOT, SWAP, FUTURES)"
    ),
    inst_id: Optional[str] = Query(None, description="Instrument ID (e.g., BTC-USDT)"),
    limit: int = Query(default=100, ge=1, le=100, description="Number of results (1-100)"),
) -> Dict[str, Any]:
    """Get order history.

    Args:
        mode: Trading mode (demo or live)
        inst_type: Instrument type
        inst_id: Optional instrument ID filter
        limit: Number of results (1-100)

    Returns:
        Dictionary with mode and orders list

    Raises:
        HTTPException: 401 for auth errors, 429 for rate limits, 400 for other errors
    """
    try:
        logger.info(
            f"Getting order history - mode: {mode}, inst_type: {inst_type}, inst_id: {inst_id}, limit: {limit}"
        )
        client = get_okx_client(mode)
        orders = await client.get_order_history(inst_type=inst_type, inst_id=inst_id, limit=limit)
        logger.info(f"Order history retrieved successfully - {len(orders)} orders")
        return {"mode": mode, "orders": orders}
    except OKXAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.error(f"Rate limit error: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXInsufficientBalanceError as e:
        logger.error(f"Insufficient balance error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
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
    inst_type: Optional[str] = Query(
        default=None, description="Instrument type (e.g., SWAP, FUTURES, SPOT)"
    ),
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
