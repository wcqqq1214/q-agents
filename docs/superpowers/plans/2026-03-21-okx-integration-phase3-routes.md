# OKX集成 - Phase 3: 路由层和集成测试（Task 10-12）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现FastAPI路由层，提供RESTful API接口，并完成端到端集成测试

**Prerequisites:** Phase 1（Task 1-5）和 Phase 2（Task 6-9）已完成

**Architecture:** FastAPI路由层调用OKXTradingClient，提供统一的HTTP接口

**Tech Stack:** FastAPI, pytest, TestClient

---

## 路由设计

### API端点规划

```
/api/okx/account/balance          GET    获取账户余额
/api/okx/account/positions        GET    获取持仓信息

/api/okx/trade/order              POST   下单
/api/okx/trade/order/{order_id}   DELETE 撤单
/api/okx/trade/order/{order_id}   GET    查询订单详情
/api/okx/trade/orders/history     GET    查询历史订单
```

### 通用参数

所有接口都支持`mode`查询参数：
- `mode=demo` - 使用模拟盘（默认）
- `mode=live` - 使用实盘

---

## Task 10: API路由 - 账户管理

**Files:**
- Create: `app/api/routes/okx.py`
- Modify: `app/api/main.py`
- Create: `tests/test_okx_routes_account.py`

### Step 1: 编写账户路由测试

Create `tests/test_okx_routes_account.py`:

```python
"""测试OKX账户路由"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.api.main import app

client = TestClient(app)


@pytest.fixture
def mock_okx_client():
    """Mock OKX客户端"""
    with patch('app.api.routes.okx.get_okx_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        yield mock_client


def test_get_balance_all_currencies(mock_okx_client):
    """测试获取所有币种余额"""
    mock_okx_client.get_account_balance = AsyncMock(return_value=[
        {
            'currency': 'USDT',
            'available': '1000.5',
            'frozen': '100.0',
            'total': '1100.5'
        },
        {
            'currency': 'BTC',
            'available': '0.5',
            'frozen': '0',
            'total': '0.5'
        }
    ])

    response = client.get("/api/okx/account/balance?mode=demo")
    
    assert response.status_code == 200
    data = response.json()
    assert data['mode'] == 'demo'
    assert len(data['balances']) == 2
    assert data['balances'][0]['currency'] == 'USDT'
    assert data['balances'][0]['total'] == '1100.5'


def test_get_balance_single_currency(mock_okx_client):
    """测试获取单个币种余额"""
    mock_okx_client.get_account_balance = AsyncMock(return_value=[
        {
            'currency': 'USDT',
            'available': '1000.5',
            'frozen': '100.0',
            'total': '1100.5'
        }
    ])

    response = client.get("/api/okx/account/balance?mode=demo&currency=USDT")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data['balances']) == 1
    assert data['balances'][0]['currency'] == 'USDT'


def test_get_balance_auth_error(mock_okx_client):
    """测试认证错误"""
    from app.okx.exceptions import OKXAuthError
    
    mock_okx_client.get_account_balance = AsyncMock(
        side_effect=OKXAuthError("Invalid Sign", code="50113")
    )

    response = client.get("/api/okx/account/balance?mode=demo")
    
    assert response.status_code == 401
    assert "Invalid Sign" in response.json()['detail']


def test_get_balance_rate_limit(mock_okx_client):
    """测试频率限制"""
    from app.okx.exceptions import OKXRateLimitError
    
    mock_okx_client.get_account_balance = AsyncMock(
        side_effect=OKXRateLimitError("Rate limit exceeded", code="50011")
    )

    response = client.get("/api/okx/account/balance?mode=demo")
    
    assert response.status_code == 429
    assert "Rate limit" in response.json()['detail']


def test_get_balance_invalid_mode():
    """测试无效的mode参数"""
    response = client.get("/api/okx/account/balance?mode=invalid")
    
    assert response.status_code == 400


def test_get_positions_all(mock_okx_client):
    """测试获取所有持仓"""
    mock_okx_client.get_positions = AsyncMock(return_value=[
        {
            'inst_id': 'BTC-USDT-SWAP',
            'position_side': 'long',
            'position': '10',
            'available_position': '10',
            'average_price': '50000',
            'unrealized_pnl': '500',
            'leverage': '10'
        }
    ])

    response = client.get("/api/okx/account/positions?mode=demo")
    
    assert response.status_code == 200
    data = response.json()
    assert data['mode'] == 'demo'
    assert len(data['positions']) == 1
    assert data['positions'][0]['inst_id'] == 'BTC-USDT-SWAP'


def test_get_positions_by_inst_type(mock_okx_client):
    """测试按产品类型获取持仓"""
    mock_okx_client.get_positions = AsyncMock(return_value=[])

    response = client.get("/api/okx/account/positions?mode=demo&inst_type=SPOT")
    
    assert response.status_code == 200
    data = response.json()
    assert data['positions'] == []


def test_get_positions_error(mock_okx_client):
    """测试持仓查询错误"""
    from app.okx.exceptions import OKXError
    
    mock_okx_client.get_positions = AsyncMock(
        side_effect=OKXError("API error", code="50000")
    )

    response = client.get("/api/okx/account/positions?mode=demo")
    
    assert response.status_code == 400
```

### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_routes_account.py -v
```

Expected: 测试失败，提示路由不存在

### Step 3: 创建OKX路由文件

Create `app/api/routes/okx.py`:

```python
"""OKX API路由"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
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
    mode: str = Query("demo", description="交易模式 (live/demo)"),
    currency: Optional[str] = Query(None, description="币种，如BTC、USDT")
):
    """获取账户余额
    
    Args:
        mode: 交易模式，demo=模拟盘，live=实盘
        currency: 币种（可选），不传则返回所有币种
        
    Returns:
        {
            "mode": "demo",
            "balances": [
                {
                    "currency": "USDT",
                    "available": "1000.5",
                    "frozen": "100.0",
                    "total": "1100.5"
                }
            ]
        }
    """
    try:
        client = get_okx_client(mode)
        balances = await client.get_account_balance(currency)
        
        logger.info(f"[OKX-{mode.upper()}] Balance query: {len(balances)} currencies")
        
        return {
            "mode": mode,
            "balances": balances
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/okx/account/positions")
async def get_positions(
    mode: str = Query("demo", description="交易模式 (live/demo)"),
    inst_type: Optional[str] = Query(None, description="产品类型 (SPOT/MARGIN/SWAP/FUTURES/OPTION)")
):
    """获取持仓信息
    
    Args:
        mode: 交易模式，demo=模拟盘，live=实盘
        inst_type: 产品类型（可选）
        
    Returns:
        {
            "mode": "demo",
            "positions": [
                {
                    "inst_id": "BTC-USDT-SWAP",
                    "position_side": "long",
                    "position": "10",
                    "available_position": "10",
                    "average_price": "50000",
                    "unrealized_pnl": "500",
                    "leverage": "10"
                }
            ]
        }
    """
    try:
        client = get_okx_client(mode)
        positions = await client.get_positions(inst_type)
        
        logger.info(f"[OKX-{mode.upper()}] Positions query: {len(positions)} positions")
        
        return {
            "mode": mode,
            "positions": positions
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")
```


### Step 4: 注册路由到main.py

在 `app/api/main.py` 中添加：

```python
from app.api.routes import okx

# 注册OKX路由
app.include_router(okx.router, prefix="/api", tags=["okx"])
```

### Step 5: 运行测试验证

```bash
uv run pytest tests/test_okx_routes_account.py -v
```

Expected: 所有测试通过

### Step 6: 提交账户路由

```bash
git add app/api/routes/okx.py app/api/main.py tests/test_okx_routes_account.py
git commit -m "feat(okx): add account management routes"
```

---

## Task 11: API路由 - 交易管理

**Files:**
- Modify: `app/api/routes/okx.py`
- Create: `tests/test_okx_routes_trade.py`

### Step 1: 编写交易路由测试

Create `tests/test_okx_routes_trade.py`:

```python
"""测试OKX交易路由"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.api.main import app

client = TestClient(app)


@pytest.fixture
def mock_okx_client():
    """Mock OKX客户端"""
    with patch('app.api.routes.okx.get_okx_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        yield mock_client


def test_place_limit_order(mock_okx_client):
    """测试限价单"""
    mock_okx_client.place_order = AsyncMock(return_value={
        'order_id': '123456',
        'client_order_id': 'my-order-1',
        'status_code': '0'
    })

    response = client.post("/api/okx/trade/order", json={
        'mode': 'demo',
        'inst_id': 'BTC-USDT',
        'side': 'buy',
        'order_type': 'limit',
        'size': '0.01',
        'price': '50000'
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data['order_id'] == '123456'
    assert data['mode'] == 'demo'


def test_place_market_order(mock_okx_client):
    """测试市价单"""
    mock_okx_client.place_order = AsyncMock(return_value={
        'order_id': '123457',
        'client_order_id': '',
        'status_code': '0'
    })

    response = client.post("/api/okx/trade/order", json={
        'mode': 'demo',
        'inst_id': 'BTC-USDT',
        'side': 'sell',
        'order_type': 'market',
        'size': '0.01'
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data['order_id'] == '123457'


def test_place_order_insufficient_balance(mock_okx_client):
    """测试余额不足"""
    from app.okx.exceptions import OKXInsufficientBalanceError
    
    mock_okx_client.place_order = AsyncMock(
        side_effect=OKXInsufficientBalanceError("Insufficient balance", code="51008")
    )

    response = client.post("/api/okx/trade/order", json={
        'mode': 'demo',
        'inst_id': 'BTC-USDT',
        'side': 'buy',
        'order_type': 'market',
        'size': '100'
    })
    
    assert response.status_code == 400
    assert "Insufficient balance" in response.json()['detail']


def test_place_order_validation_error():
    """测试请求参数验证"""
    response = client.post("/api/okx/trade/order", json={
        'mode': 'demo',
        'inst_id': 'BTC-USDT',
        'side': 'buy',
        # 缺少必需的order_type和size
    })
    
    assert response.status_code == 422


def test_cancel_order(mock_okx_client):
    """测试撤单"""
    mock_okx_client.cancel_order = AsyncMock(return_value={
        'order_id': '123456',
        'client_order_id': '',
        'status_code': '0'
    })

    response = client.delete(
        "/api/okx/trade/order/123456?mode=demo&inst_id=BTC-USDT"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['order_id'] == '123456'
    assert data['mode'] == 'demo'


def test_cancel_order_not_found(mock_okx_client):
    """测试撤单失败（订单不存在）"""
    from app.okx.exceptions import OKXOrderError
    
    mock_okx_client.cancel_order = AsyncMock(
        side_effect=OKXOrderError("Order does not exist", code="51400")
    )

    response = client.delete(
        "/api/okx/trade/order/999999?mode=demo&inst_id=BTC-USDT"
    )
    
    assert response.status_code == 400


def test_get_order_details(mock_okx_client):
    """测试查询订单详情"""
    mock_okx_client.get_order_details = AsyncMock(return_value={
        'order_id': '123456',
        'client_order_id': 'my-order-1',
        'inst_id': 'BTC-USDT',
        'status': 'filled',
        'side': 'buy',
        'order_type': 'limit',
        'size': '0.01',
        'filled_size': '0.01',
        'price': '50000',
        'average_price': '50000',
        'timestamp': '1710000000000'
    })

    response = client.get(
        "/api/okx/trade/order/123456?mode=demo&inst_id=BTC-USDT"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['order']['order_id'] == '123456'
    assert data['order']['status'] == 'filled'
    assert data['mode'] == 'demo'


def test_get_order_history(mock_okx_client):
    """测试查询历史订单"""
    mock_okx_client.get_order_history = AsyncMock(return_value=[
        {
            'order_id': '123456',
            'inst_id': 'BTC-USDT',
            'status': 'filled',
            'side': 'buy',
            'order_type': 'market',
            'size': '0.01',
            'filled_size': '0.01',
            'price': None,
            'average_price': '50000',
            'timestamp': '1710000000000'
        },
        {
            'order_id': '123457',
            'inst_id': 'ETH-USDT',
            'status': 'canceled',
            'side': 'sell',
            'order_type': 'limit',
            'size': '1',
            'filled_size': '0',
            'price': '3000',
            'average_price': None,
            'timestamp': '1710000100000'
        }
    ])

    response = client.get(
        "/api/okx/trade/orders/history?mode=demo&inst_type=SPOT&limit=10"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['mode'] == 'demo'
    assert len(data['orders']) == 2
    assert data['orders'][0]['order_id'] == '123456'


def test_get_order_history_empty(mock_okx_client):
    """测试空历史订单"""
    mock_okx_client.get_order_history = AsyncMock(return_value=[])

    response = client.get(
        "/api/okx/trade/orders/history?mode=demo&inst_type=SPOT"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['orders'] == []
```

### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_routes_trade.py -v
```

### Step 3: 在okx.py中添加交易路由

在 `app/api/routes/okx.py` 中添加：

```python
from pydantic import BaseModel, Field
from app.okx.exceptions import OKXInsufficientBalanceError, OKXOrderError


# 请求模型
class PlaceOrderRequest(BaseModel):
    """下单请求"""
    mode: str = Field(..., description="交易模式 (live/demo)")
    inst_id: str = Field(..., description="产品ID，如BTC-USDT")
    side: str = Field(..., description="订单方向 (buy/sell)")
    order_type: str = Field(..., description="订单类型 (market/limit/post_only/fok/ioc)")
    size: str = Field(..., description="委托数量")
    price: Optional[str] = Field(None, description="委托价格（限价单必填）")
    client_order_id: Optional[str] = Field(None, description="客户端订单ID")


@router.post("/okx/trade/order")
async def place_order(request: PlaceOrderRequest):
    """下单
    
    Args:
        request: 下单请求参数
        
    Returns:
        {
            "mode": "demo",
            "order_id": "123456",
            "client_order_id": "my-order-1",
            "status_code": "0"
        }
    """
    try:
        client = get_okx_client(request.mode)
        result = await client.place_order(
            inst_id=request.inst_id,
            side=request.side,
            order_type=request.order_type,
            size=request.size,
            price=request.price,
            client_order_id=request.client_order_id
        )
        
        logger.info(
            f"[OKX-{request.mode.upper()}] Order placed: "
            f"{request.inst_id} {request.side} {request.size} @ {request.price or 'market'}"
        )
        
        return {
            "mode": request.mode,
            **result
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{request.mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{request.mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXInsufficientBalanceError as e:
        logger.warning(f"[OKX-{request.mode.upper()}] Insufficient balance: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"[OKX-{request.mode.upper()}] Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{request.mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{request.mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{request.mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/okx/trade/order/{order_id}")
async def cancel_order(
    order_id: str,
    mode: str = Query("demo", description="交易模式 (live/demo)"),
    inst_id: str = Query(..., description="产品ID"),
    client_order_id: Optional[str] = Query(None, description="客户端订单ID")
):
    """撤单
    
    Args:
        order_id: 订单ID（路径参数）
        mode: 交易模式
        inst_id: 产品ID
        client_order_id: 客户端订单ID（可选，与order_id二选一）
        
    Returns:
        {
            "mode": "demo",
            "order_id": "123456",
            "client_order_id": "",
            "status_code": "0"
        }
    """
    try:
        client = get_okx_client(mode)
        result = await client.cancel_order(
            inst_id=inst_id,
            order_id=order_id if order_id != "by-client-id" else None,
            client_order_id=client_order_id
        )
        
        logger.info(f"[OKX-{mode.upper()}] Order canceled: {order_id or client_order_id}")
        
        return {
            "mode": mode,
            **result
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"[OKX-{mode.upper()}] Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/okx/trade/order/{order_id}")
async def get_order_details(
    order_id: str,
    mode: str = Query("demo", description="交易模式 (live/demo)"),
    inst_id: str = Query(..., description="产品ID"),
    client_order_id: Optional[str] = Query(None, description="客户端订单ID")
):
    """查询订单详情
    
    Args:
        order_id: 订单ID（路径参数）
        mode: 交易模式
        inst_id: 产品ID
        client_order_id: 客户端订单ID（可选）
        
    Returns:
        {
            "mode": "demo",
            "order": {
                "order_id": "123456",
                "inst_id": "BTC-USDT",
                "status": "filled",
                ...
            }
        }
    """
    try:
        client = get_okx_client(mode)
        order = await client.get_order_details(
            inst_id=inst_id,
            order_id=order_id if order_id != "by-client-id" else None,
            client_order_id=client_order_id
        )
        
        logger.info(f"[OKX-{mode.upper()}] Order query: {order_id or client_order_id}")
        
        return {
            "mode": mode,
            "order": order
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXOrderError as e:
        logger.error(f"[OKX-{mode.upper()}] Order error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/okx/trade/orders/history")
async def get_order_history(
    mode: str = Query("demo", description="交易模式 (live/demo)"),
    inst_type: str = Query("SPOT", description="产品类型 (SPOT/MARGIN/SWAP/FUTURES)"),
    inst_id: Optional[str] = Query(None, description="产品ID"),
    limit: int = Query(100, ge=1, le=100, description="返回数量限制")
):
    """查询历史订单
    
    Args:
        mode: 交易模式
        inst_type: 产品类型
        inst_id: 产品ID（可选）
        limit: 返回数量限制
        
    Returns:
        {
            "mode": "demo",
            "orders": [...]
        }
    """
    try:
        client = get_okx_client(mode)
        orders = await client.get_order_history(
            inst_type=inst_type,
            inst_id=inst_id,
            limit=limit
        )
        
        logger.info(f"[OKX-{mode.upper()}] Order history query: {len(orders)} orders")
        
        return {
            "mode": mode,
            "orders": orders
        }
    except OKXAuthError as e:
        logger.error(f"[OKX-{mode.upper()}] Auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except OKXRateLimitError as e:
        logger.warning(f"[OKX-{mode.upper()}] Rate limit: {e}")
        raise HTTPException(status_code=429, detail=str(e))
    except OKXConfigError as e:
        logger.error(f"[OKX-{mode.upper()}] Config error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except OKXError as e:
        logger.error(f"[OKX-{mode.upper()}] API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[OKX-{mode.upper()}] Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")
```


### Step 4: 运行测试验证

```bash
uv run pytest tests/test_okx_routes_trade.py -v
```

Expected: 所有测试通过

### Step 5: 提交交易路由

```bash
git add app/api/routes/okx.py tests/test_okx_routes_trade.py
git commit -m "feat(okx): add trading routes (order, cancel, query)"
```

---

## Task 12: 集成测试和文档

**Files:**
- Create: `tests/integration/test_okx_integration.py`
- Create: `docs/okx-api-guide.md`

### Step 1: 编写端到端集成测试

Create `tests/integration/test_okx_integration.py`:

```python
"""OKX集成端到端测试（使用模拟盘）"""
import pytest
import asyncio
from app.okx import get_okx_client, clear_client_cache


@pytest.fixture(scope="module")
def okx_client():
    """获取OKX模拟盘客户端"""
    client = get_okx_client(mode="demo")
    yield client
    clear_client_cache()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_account_balance_integration(okx_client):
    """集成测试：获取账户余额"""
    balances = await okx_client.get_account_balance()
    
    # 验证返回格式
    assert isinstance(balances, list)
    if len(balances) > 0:
        balance = balances[0]
        assert 'currency' in balance
        assert 'available' in balance
        assert 'frozen' in balance
        assert 'total' in balance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_positions_integration(okx_client):
    """集成测试：获取持仓"""
    positions = await okx_client.get_positions(inst_type='SPOT')
    
    # 验证返回格式
    assert isinstance(positions, list)
    # 模拟盘可能没有持仓，所以不强制要求有数据


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_lifecycle_integration(okx_client):
    """集成测试：订单生命周期（下单 → 查询 → 撤单）"""
    
    # 1. 下单（限价单，价格设置得很低，不会成交）
    order_result = await okx_client.place_order(
        inst_id='BTC-USDT',
        side='buy',
        order_type='limit',
        size='0.001',  # 最小数量
        price='10000',  # 远低于市价，不会成交
        client_order_id=f'test-{asyncio.get_event_loop().time()}'
    )
    
    assert 'order_id' in order_result
    order_id = order_result['order_id']
    print(f"Order placed: {order_id}")
    
    # 等待订单进入系统
    await asyncio.sleep(1)
    
    # 2. 查询订单详情
    order_details = await okx_client.get_order_details(
        inst_id='BTC-USDT',
        order_id=order_id
    )
    
    assert order_details['order_id'] == order_id
    assert order_details['inst_id'] == 'BTC-USDT'
    assert order_details['side'] == 'buy'
    assert order_details['status'] in ['live', 'partially_filled']
    print(f"Order status: {order_details['status']}")
    
    # 3. 撤单
    cancel_result = await okx_client.cancel_order(
        inst_id='BTC-USDT',
        order_id=order_id
    )
    
    assert cancel_result['order_id'] == order_id
    print(f"Order canceled: {order_id}")
    
    # 等待撤单生效
    await asyncio.sleep(1)
    
    # 4. 再次查询，验证已撤单
    order_details_after = await okx_client.get_order_details(
        inst_id='BTC-USDT',
        order_id=order_id
    )
    
    assert order_details_after['status'] == 'canceled'
    print(f"Order final status: {order_details_after['status']}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_order_history_integration(okx_client):
    """集成测试：查询历史订单"""
    orders = await okx_client.get_order_history(
        inst_type='SPOT',
        limit=10
    )
    
    # 验证返回格式
    assert isinstance(orders, list)
    if len(orders) > 0:
        order = orders[0]
        assert 'order_id' in order
        assert 'inst_id' in order
        assert 'status' in order
        assert 'side' in order


@pytest.mark.integration
def test_client_singleton():
    """集成测试：客户端单例模式"""
    client1 = get_okx_client(mode="demo")
    client2 = get_okx_client(mode="demo")
    
    # 应该返回同一个实例
    assert client1 is client2
    
    # 强制刷新后应该是新实例
    client3 = get_okx_client(mode="demo", force_refresh=True)
    assert client3 is not client1
    
    clear_client_cache()
```

**运行集成测试：**

```bash
# 运行集成测试（需要真实的OKX模拟盘凭证）
uv run pytest tests/integration/test_okx_integration.py -v -m integration

# 跳过集成测试（仅运行单元测试）
uv run pytest tests/ -v -m "not integration"
```

### Step 2: 编写API使用文档

Create `docs/okx-api-guide.md`:

```markdown
# OKX API 使用指南

## 概述

Finance Agent集成了OKX交易所API，支持实盘和模拟盘的账户管理和交易功能。

## 配置

### 环境变量

在`.env`文件中配置OKX API凭证：

\`\`\`bash
# OKX模拟盘配置
OKX_DEMO_API_KEY=your-demo-api-key
OKX_DEMO_SECRET_KEY=your-demo-secret-key
OKX_DEMO_PASSPHRASE=your-demo-passphrase

# OKX实盘配置
OKX_LIVE_API_KEY=your-live-api-key
OKX_LIVE_SECRET_KEY=your-live-secret-key
OKX_LIVE_PASSPHRASE=your-live-passphrase

# 默认模式
OKX_DEFAULT_MODE=demo
\`\`\`

### 获取API凭证

1. 登录OKX官网
2. 进入"API管理"页面
3. 创建API Key（分别为实盘和模拟盘创建）
4. 保存API Key、Secret Key和Passphrase

**注意：** 实盘和模拟盘的API凭证是完全独立的。

## API端点

### 账户管理

#### 获取账户余额

\`\`\`bash
GET /api/okx/account/balance?mode=demo&currency=USDT
\`\`\`

**参数：**
- `mode`: 交易模式（demo/live），默认demo
- `currency`: 币种（可选），不传则返回所有币种

**响应：**
\`\`\`json
{
  "mode": "demo",
  "balances": [
    {
      "currency": "USDT",
      "available": "1000.5",
      "frozen": "100.0",
      "total": "1100.5"
    }
  ]
}
\`\`\`

#### 获取持仓信息

\`\`\`bash
GET /api/okx/account/positions?mode=demo&inst_type=SPOT
\`\`\`

**参数：**
- `mode`: 交易模式（demo/live）
- `inst_type`: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）

**响应：**
\`\`\`json
{
  "mode": "demo",
  "positions": [
    {
      "inst_id": "BTC-USDT-SWAP",
      "position_side": "long",
      "position": "10",
      "available_position": "10",
      "average_price": "50000",
      "unrealized_pnl": "500",
      "leverage": "10"
    }
  ]
}
\`\`\`

### 交易管理

#### 下单

\`\`\`bash
POST /api/okx/trade/order
Content-Type: application/json

{
  "mode": "demo",
  "inst_id": "BTC-USDT",
  "side": "buy",
  "order_type": "limit",
  "size": "0.01",
  "price": "50000",
  "client_order_id": "my-order-1"
}
\`\`\`

**参数：**
- `mode`: 交易模式
- `inst_id`: 产品ID（如BTC-USDT）
- `side`: 订单方向（buy/sell）
- `order_type`: 订单类型（market/limit/post_only/fok/ioc）
- `size`: 委托数量
- `price`: 委托价格（限价单必填）
- `client_order_id`: 客户端订单ID（可选）

**响应：**
\`\`\`json
{
  "mode": "demo",
  "order_id": "123456",
  "client_order_id": "my-order-1",
  "status_code": "0"
}
\`\`\`

#### 撤单

\`\`\`bash
DELETE /api/okx/trade/order/123456?mode=demo&inst_id=BTC-USDT
\`\`\`

**参数：**
- `order_id`: 订单ID（路径参数）
- `mode`: 交易模式
- `inst_id`: 产品ID

**响应：**
\`\`\`json
{
  "mode": "demo",
  "order_id": "123456",
  "status_code": "0"
}
\`\`\`

#### 查询订单详情

\`\`\`bash
GET /api/okx/trade/order/123456?mode=demo&inst_id=BTC-USDT
\`\`\`

**响应：**
\`\`\`json
{
  "mode": "demo",
  "order": {
    "order_id": "123456",
    "inst_id": "BTC-USDT",
    "status": "filled",
    "side": "buy",
    "order_type": "limit",
    "size": "0.01",
    "filled_size": "0.01",
    "price": "50000",
    "average_price": "50000",
    "timestamp": "1710000000000"
  }
}
\`\`\`

#### 查询历史订单

\`\`\`bash
GET /api/okx/trade/orders/history?mode=demo&inst_type=SPOT&limit=10
\`\`\`

**参数：**
- `mode`: 交易模式
- `inst_type`: 产品类型
- `inst_id`: 产品ID（可选）
- `limit`: 返回数量限制（1-100）

**响应：**
\`\`\`json
{
  "mode": "demo",
  "orders": [...]
}
\`\`\`

## 错误处理

### HTTP状态码

- `200`: 成功
- `400`: 请求错误（参数错误、业务错误）
- `401`: 认证错误（API密钥无效）
- `429`: 频率限制
- `500`: 服务器错误

### 错误响应格式

\`\`\`json
{
  "detail": "[50113] Invalid Sign"
}
\`\`\`

## Python客户端使用

### 基本使用

\`\`\`python
from app.okx import get_okx_client

# 获取客户端
client = get_okx_client(mode="demo")

# 查询余额
balances = await client.get_account_balance()

# 下单
order = await client.place_order(
    inst_id="BTC-USDT",
    side="buy",
    order_type="limit",
    size="0.01",
    price="50000"
)

# 撤单
await client.cancel_order(
    inst_id="BTC-USDT",
    order_id=order['order_id']
)
\`\`\`

### 错误处理

\`\`\`python
from app.okx.exceptions import (
    OKXAuthError,
    OKXRateLimitError,
    OKXInsufficientBalanceError,
    OKXOrderError
)

try:
    order = await client.place_order(...)
except OKXAuthError as e:
    print(f"认证错误: {e}")
except OKXRateLimitError as e:
    print(f"频率限制: {e}")
except OKXInsufficientBalanceError as e:
    print(f"余额不足: {e}")
except OKXOrderError as e:
    print(f"订单错误: {e}")
\`\`\`

## 最佳实践

1. **使用模拟盘测试**：在实盘交易前，先在模拟盘充分测试
2. **错误处理**：始终捕获并处理异常
3. **频率限制**：注意API调用频率，避免触发限制
4. **日志记录**：记录所有交易操作，便于审计
5. **凭证安全**：不要将API密钥提交到版本控制

## 常见问题

### Q: 如何切换实盘和模拟盘？

A: 通过`mode`参数控制：`mode=demo`使用模拟盘，`mode=live`使用实盘。

### Q: 签名错误怎么办？

A: 检查API Key、Secret Key和Passphrase是否正确，确保实盘和模拟盘的凭证不要混淆。

### Q: 如何处理频率限制？

A: 客户端已内置重试机制，会自动重试频率限制错误。如果频繁触发，需要降低调用频率。

### Q: 市价单和限价单的区别？

A: 市价单立即以市场价成交，不需要指定价格；限价单以指定价格挂单，可能不会立即成交。
\`\`\`

### Step 3: 运行完整测试套件

```bash
# 运行所有单元测试
uv run pytest tests/test_okx*.py tests/test_config_manager_okx.py -v

# 运行集成测试（需要真实凭证）
uv run pytest tests/integration/test_okx_integration.py -v -m integration

# 查看测试覆盖率
uv run pytest tests/ --cov=app/okx --cov-report=html
```

### Step 4: 提交集成测试和文档

```bash
git add tests/integration/test_okx_integration.py docs/okx-api-guide.md
git commit -m "feat(okx): add integration tests and API documentation"
```

---

## Phase 3 完成标准

- [ ] Task 10: API路由 - 账户管理 ✅
- [ ] Task 11: API路由 - 交易管理 ✅
- [ ] Task 12: 集成测试和文档 ✅

**完成后：** OKX集成全部完成！

---

## 验收标准

1. 所有单元测试通过
2. 集成测试通过（使用模拟盘）
3. API文档完整
4. 错误处理完善
5. 日志记录清晰

---

## 最终测试清单

- [ ] 账户余额查询（所有币种 + 单个币种）
- [ ] 持仓查询（所有类型 + 指定类型）
- [ ] 限价单下单
- [ ] 市价单下单
- [ ] 撤单
- [ ] 查询订单详情
- [ ] 查询历史订单
- [ ] 认证错误处理
- [ ] 频率限制处理
- [ ] 余额不足处理
- [ ] 订单错误处理
- [ ] 实盘/模拟盘切换

---

## 部署注意事项

1. **环境变量**：确保生产环境配置了正确的API凭证
2. **日志级别**：生产环境建议使用INFO级别
3. **监控告警**：监控API调用成功率和频率限制
4. **备份策略**：定期备份交易记录
5. **安全审计**：定期审查API密钥权限

