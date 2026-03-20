# OKX交易API集成设计文档

## 1. 概述

### 1.1 项目背景
Finance Agent是一个多代理金融分析系统，目前已集成股票行情数据（通过yfinance和MCP）、Polymarket预测市场数据等。为了扩展系统的交易能力，需要集成OKX交易所API，支持加密货币的实盘和模拟盘交易。

### 1.2 集成目标
- 支持OKX实盘（live）和模拟盘（demo）API接入
- 提供账户管理、交易执行、行情查询等完整功能
- 通过FastAPI提供RESTful接口供前端调用
- 支持通过环境变量和前端设置页面管理API密钥
- 生成完整的API文档记录

### 1.3 技术选型
- **OKX SDK**: 使用 `python-okx` 包 (https://pypi.org/project/python-okx/) 或 `okx` 包 (https://pypi.org/project/okx/)
  - 推荐使用 `python-okx` (更活跃维护)
  - 备选方案：`okx` 包 (pyted/okx)
- **架构模式**: Client-Routes分层架构（与现有Polymarket集成保持一致）
- **配置管理**: 扩展现有ConfigManager支持OKX配置
- **API框架**: FastAPI（现有技术栈）

## 2. 架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│                     (暂不实现UI界面)                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  app/api/routes/okx.py (路由层)                       │  │
│  │  - GET  /api/okx/account/balance                      │  │
│  │  - GET  /api/okx/account/positions                    │  │
│  │  - POST /api/okx/trade/order                          │  │
│  │  - GET  /api/okx/market/ticker                        │  │
│  │  - ...                                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                               │
│                              ▼                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  app/okx/trading_client.py (业务逻辑层)               │  │
│  │  - OKXTradingClient 类                                │  │
│  │  - 封装 OKX SDK 调用                                  │  │
│  │  - 实盘/模拟盘切换逻辑                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                               │
│                              ▼                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  OKX Official Python SDK                              │  │
│  │  (okx package)                                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    OKX API Servers                           │
│  - 实盘: https://www.okx.com                                 │
│  - 模拟盘: https://www.okx.com (demo=true)                   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块划分

**核心模块：**

1. **app/okx/trading_client.py** - OKX客户端封装
   - OKXTradingClient类
   - 封装OKX SDK调用
   - 实盘/模拟盘切换逻辑

2. **app/okx/__init__.py** - 模块初始化
   - 导出公共接口

3. **app/api/routes/okx.py** - API路由层
   - 账户管理路由
   - 交易管理路由
   - 行情数据路由
   - 系统管理路由

4. **app/api/models/schemas.py** - 数据模型（扩展）
   - OKX相关的Pydantic模型

5. **app/config_manager.py** - 配置管理（扩展）
   - OKX配置读取和更新

### 2.3 数据流向

```
用户请求 → FastAPI路由 → OKXTradingClient → OKX SDK → OKX API服务器
         ←              ←                   ←          ←
```

## 3. 配置管理

### 3.1 环境变量配置

**.env文件格式：**

```bash
# OKX Live Trading API (实盘)
OKX_LIVE_API_KEY=your-live-api-key
OKX_LIVE_SECRET_KEY=your-live-secret-key
OKX_LIVE_PASSPHRASE=your-live-passphrase

# OKX Demo Trading API (模拟盘)
OKX_DEMO_API_KEY=923cc63f-d44d-4726-9767-c2237538a36e
OKX_DEMO_SECRET_KEY=5C45AEA155CD0A29B91C26B510D95AB9
OKX_DEMO_PASSPHRASE=200312142058Wcq.

# Default mode: live or demo
OKX_DEFAULT_MODE=demo
```

### 3.2 实盘/模拟盘切换机制

- 通过API请求的 `mode` 查询参数指定（live/demo）
- 如果未指定，使用 `OKX_DEFAULT_MODE` 环境变量
- 所有API响应中包含当前使用的mode标识

### 3.3 前端设置接口

**获取OKX配置：**
```
GET /api/settings/okx?mode={live|demo}
```

**响应示例：**
```json
{
  "mode": "demo",
  "api_key": "923cc63f-d44d-4726-9767-c2237538a36e",
  "secret_key": "5C45AEA155CD0A29B91C26B510D95AB9",
  "passphrase": "200312142058Wcq."
}
```

**更新OKX配置：**
```
PUT /api/settings/okx
```

**请求体：**
```json
{
  "mode": "live",
  "api_key": "...",
  "secret_key": "...",
  "passphrase": "..."
}
```

**响应示例：**
```json
{
  "mode": "live",
  "api_key": "new-api-key",
  "secret_key": "new-secret-key",
  "passphrase": "new-passphrase",
  "updated_at": "2026-03-20T10:30:00Z"
}
```

**注意**: 这些设置接口通过扩展现有的 `app/api/routes/settings.py` 实现，详见第10节部署说明。

## 4. 核心类设计

### 4.1 OKXTradingClient 类

**文件位置：** `app/okx/trading_client.py`

**类定义：**

```python
from python_okx import Account, Trade, MarketData  # 假设使用 python-okx 包

class OKXTradingClient:
    """OKX交易客户端，封装OKX SDK调用"""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        is_demo: bool = False
    ):
        """初始化客户端

        Args:
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码
            is_demo: 是否为模拟盘
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_demo = is_demo

        # 初始化OKX SDK客户端
        # 注意：具体初始化方式需要根据实际使用的SDK包调整
        self.account_api = Account(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag="1" if is_demo else "0"  # 1=模拟盘, 0=实盘
        )
        self.trade_api = Trade(
            api_key=api_key,
            api_secret_key=secret_key,
            passphrase=passphrase,
            flag="1" if is_demo else "0"
        )
        self.market_api = MarketData()  # 行情API通常不需要认证
```

**账户管理方法：**

```python
async def get_account_balance(
    self,
    currency: Optional[str] = None
) -> Dict:
    """获取账户余额

    Args:
        currency: 币种，如BTC、USDT，不传则返回所有币种

    Returns:
        余额信息字典
    """

async def get_positions(
    self,
    inst_type: Optional[str] = None
) -> List[Dict]:
    """获取持仓信息

    Args:
        inst_type: 产品类型 SPOT/MARGIN/SWAP/FUTURES/OPTION

    Returns:
        持仓列表
    """

async def get_account_config(self) -> Dict:
    """获取账户配置

    Returns:
        账户配置信息
    """
```

**交易管理方法：**

```python
async def place_order(
    self,
    inst_id: str,
    side: str,
    order_type: str,
    size: str,
    price: Optional[str] = None,
    **kwargs
) -> Dict:
    """下单

    Args:
        inst_id: 产品ID，如 BTC-USDT
        side: 订单方向 buy/sell
        order_type: 订单类型 market/limit/post_only等
        size: 委托数量
        price: 委托价格（限价单必填）
        **kwargs: 其他参数（止盈止损等）

    Returns:
        订单信息
    """

async def cancel_order(
    self,
    inst_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Dict:
    """撤单

    Args:
        inst_id: 产品ID
        order_id: 订单ID
        client_order_id: 客户端订单ID

    Returns:
        撤单结果
    """

async def get_order_details(
    self,
    inst_id: str,
    order_id: str
) -> Dict:
    """查询订单详情

    Args:
        inst_id: 产品ID
        order_id: 订单ID

    Returns:
        订单详情
    """

async def get_order_list(
    self,
    inst_type: Optional[str] = None
) -> List[Dict]:
    """查询订单列表

    Args:
        inst_type: 产品类型

    Returns:
        订单列表
    """
```

**行情数据方法：**

```python
async def get_ticker(self, inst_id: str) -> Dict:
    """获取单个产品ticker

    Args:
        inst_id: 产品ID

    Returns:
        Ticker数据
    """

async def get_tickers(self, inst_type: str) -> List[Dict]:
    """获取多个产品ticker

    Args:
        inst_type: 产品类型

    Returns:
        Ticker列表
    """

async def get_orderbook(
    self,
    inst_id: str,
    depth: int = 20
) -> Dict:
    """获取盘口数据

    Args:
        inst_id: 产品ID
        depth: 深度 1-400

    Returns:
        盘口数据
    """

async def get_recent_trades(
    self,
    inst_id: str,
    limit: int = 100
) -> List[Dict]:
    """获取最近成交

    Args:
        inst_id: 产品ID
        limit: 数量限制

    Returns:
        成交列表
    """

async def get_candlesticks(
    self,
    inst_id: str,
    bar: str = "1m",
    limit: int = 100
) -> List[Dict]:
    """获取K线数据

    Args:
        inst_id: 产品ID
        bar: K线周期 1m/5m/15m/30m/1H/4H/1D等
        limit: 数量限制

    Returns:
        K线数据列表
    """
```

## 5. API接口规范

### 5.1 账户管理接口

#### 获取账户余额
```
GET /api/okx/account/balance?mode={live|demo}&currency={ccy}
```

**查询参数：**
- `mode`: 模式 (live/demo)，可选，默认使用OKX_DEFAULT_MODE
- `currency`: 币种，可选，不传返回所有币种

**响应示例：**
```json
{
  "mode": "demo",
  "balances": [
    {
      "currency": "USDT",
      "available": "10000.5",
      "frozen": "100.0",
      "total": "10100.5"
    },
    {
      "currency": "BTC",
      "available": "0.5",
      "frozen": "0",
      "total": "0.5"
    }
  ]
}
```

#### 获取持仓信息
```
GET /api/okx/account/positions?mode={live|demo}&inst_type={type}
```

**查询参数：**
- `mode`: 模式 (live/demo)
- `inst_type`: 产品类型 (SPOT/MARGIN/SWAP/FUTURES/OPTION)，可选

**响应示例：**
```json
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
```

#### 获取账户配置
```
GET /api/okx/account/config?mode={live|demo}
```

**查询参数：**
- `mode`: 模式 (live/demo)

**响应示例：**
```json
{
  "mode": "demo",
  "account_level": "1",
  "position_mode": "long_short_mode",
  "auto_loan": false
}
```

### 5.2 交易管理接口

#### 下单
```
POST /api/okx/trade/order?mode={live|demo}
```

**查询参数：**
- `mode`: 模式 (live/demo)

**请求体：**
```json
{
  "inst_id": "BTC-USDT",
  "side": "buy",
  "order_type": "limit",
  "size": "0.01",
  "price": "50000",
  "client_order_id": "my-order-123"
}
```

**响应示例：**
```json
{
  "mode": "demo",
  "order_id": "123456789",
  "client_order_id": "my-order-123",
  "inst_id": "BTC-USDT",
  "status": "live",
  "side": "buy",
  "order_type": "limit",
  "size": "0.01",
  "filled_size": "0",
  "price": "50000",
  "average_price": null,
  "timestamp": "2026-03-20T10:30:00Z"
}
```

#### 撤单
```
DELETE /api/okx/trade/order?mode={live|demo}&inst_id={id}&order_id={oid}
```

**查询参数：**
- `mode`: 模式 (live/demo)
- `inst_id`: 产品ID
- `order_id`: 订单ID（与client_order_id二选一）
- `client_order_id`: 客户端订单ID（与order_id二选一）

**响应示例：**
```json
{
  "mode": "demo",
  "order_id": "123456789",
  "status": "canceled",
  "timestamp": "2026-03-20T10:35:00Z"
}
```

#### 查询订单详情
```
GET /api/okx/trade/order/{order_id}?mode={live|demo}&inst_id={id}
```

**路径参数：**
- `order_id`: 订单ID

**查询参数：**
- `mode`: 模式 (live/demo)
- `inst_id`: 产品ID

**响应示例：**
```json
{
  "mode": "demo",
  "order_id": "123456789",
  "inst_id": "BTC-USDT",
  "status": "filled",
  "side": "buy",
  "order_type": "limit",
  "size": "0.01",
  "filled_size": "0.01",
  "price": "50000",
  "average_price": "49950",
  "timestamp": "2026-03-20T10:30:00Z"
}
```

#### 查询订单列表
```
GET /api/okx/trade/orders?mode={live|demo}&inst_type={type}
```

**查询参数：**
- `mode`: 模式 (live/demo)
- `inst_type`: 产品类型，可选

**响应示例：**
```json
{
  "mode": "demo",
  "orders": [
    {
      "order_id": "123456789",
      "inst_id": "BTC-USDT",
      "status": "filled",
      "side": "buy",
      "size": "0.01",
      "filled_size": "0.01"
    }
  ]
}
```

### 5.3 行情数据接口

#### 获取单个产品ticker
```
GET /api/okx/market/ticker/{inst_id}?mode={live|demo}
```

**路径参数：**
- `inst_id`: 产品ID

**查询参数：**
- `mode`: 模式 (live/demo)

**响应示例：**
```json
{
  "mode": "demo",
  "inst_id": "BTC-USDT",
  "last": "50000",
  "bid": "49990",
  "ask": "50010",
  "volume_24h": "1234.56",
  "high_24h": "51000",
  "low_24h": "49000",
  "timestamp": "2026-03-20T10:30:00Z"
}
```

#### 获取多个产品ticker
```
GET /api/okx/market/tickers?mode={live|demo}&inst_type={type}
```

**查询参数：**
- `mode`: 模式 (live/demo)
- `inst_type`: 产品类型 (SPOT/SWAP/FUTURES等)

**响应示例：**
```json
{
  "mode": "demo",
  "tickers": [
    {
      "inst_id": "BTC-USDT",
      "last": "50000",
      "volume_24h": "1234.56"
    },
    {
      "inst_id": "ETH-USDT",
      "last": "3000",
      "volume_24h": "5678.90"
    }
  ]
}
```

#### 获取盘口数据
```
GET /api/okx/market/orderbook/{inst_id}?mode={live|demo}&depth={n}
```

**路径参数：**
- `inst_id`: 产品ID

**查询参数：**
- `mode`: 模式 (live/demo)
- `depth`: 深度 (1-400)，默认20

**响应示例：**
```json
{
  "mode": "demo",
  "inst_id": "BTC-USDT",
  "bids": [
    ["49990", "1.5"],
    ["49980", "2.0"]
  ],
  "asks": [
    ["50010", "1.2"],
    ["50020", "1.8"]
  ],
  "timestamp": "2026-03-20T10:30:00Z"
}
```

#### 获取最近成交
```
GET /api/okx/market/trades/{inst_id}?mode={live|demo}&limit={n}
```

**路径参数：**
- `inst_id`: 产品ID

**查询参数：**
- `mode`: 模式 (live/demo)
- `limit`: 数量限制，默认100

**响应示例：**
```json
{
  "mode": "demo",
  "inst_id": "BTC-USDT",
  "trades": [
    {
      "trade_id": "123456",
      "price": "50000",
      "size": "0.1",
      "side": "buy",
      "timestamp": "2026-03-20T10:30:00Z"
    }
  ]
}
```

#### 获取K线数据
```
GET /api/okx/market/candles/{inst_id}?mode={live|demo}&bar={period}&limit={n}
```

**路径参数：**
- `inst_id`: 产品ID

**查询参数：**
- `mode`: 模式 (live/demo)
- `bar`: K线周期 (1m/5m/15m/30m/1H/4H/1D等)，默认1m
- `limit`: 数量限制，默认100

**响应示例：**
```json
{
  "mode": "demo",
  "inst_id": "BTC-USDT",
  "bar": "1m",
  "candles": [
    {
      "timestamp": "2026-03-20T10:30:00Z",
      "open": "50000",
      "high": "50100",
      "low": "49900",
      "close": "50050",
      "volume": "10.5"
    }
  ]
}
```

### 5.4 系统管理接口

#### 获取当前模式
```
GET /api/okx/system/mode
```

**响应示例：**
```json
{
  "default_mode": "demo"
}
```

#### 切换默认模式
```
POST /api/okx/system/mode
```

**请求体：**
```json
{
  "mode": "live"
}
```

**响应示例：**
```json
{
  "default_mode": "live",
  "updated_at": "2026-03-20T10:30:00Z"
}
```

## 6. 数据模型定义

### 6.1 请求模型

**文件位置：** `app/api/models/schemas.py` (扩展)

```python
from pydantic import BaseModel
from typing import Optional

class OKXOrderRequest(BaseModel):
    """下单请求"""
    inst_id: str
    side: str  # buy/sell
    order_type: str  # market/limit/post_only/fok/ioc
    size: str
    price: Optional[str] = None
    client_order_id: Optional[str] = None
    reduce_only: Optional[bool] = False

class OKXCancelOrderRequest(BaseModel):
    """撤单请求"""
    inst_id: str
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
```

### 6.2 响应模型

```python
class OKXBalance(BaseModel):
    """账户余额"""
    currency: str
    available: str
    frozen: str
    total: str

class OKXPosition(BaseModel):
    """持仓信息"""
    inst_id: str
    position_side: str  # long/short/net
    position: str
    available_position: str
    average_price: str
    unrealized_pnl: str
    leverage: str

class OKXOrderResponse(BaseModel):
    """订单响应"""
    order_id: str
    client_order_id: str
    inst_id: str
    status: str  # live/partially_filled/filled/canceled
    side: str
    order_type: str
    size: str
    filled_size: str
    price: Optional[str]
    average_price: Optional[str]
    timestamp: str

class OKXTicker(BaseModel):
    """Ticker数据"""
    inst_id: str
    last: str
    bid: str
    ask: str
    volume_24h: str
    high_24h: str
    low_24h: str
    timestamp: str

class OKXOrderbook(BaseModel):
    """盘口数据"""
    inst_id: str
    bids: list  # [[price, size], ...]
    asks: list  # [[price, size], ...]
    timestamp: str

class OKXTrade(BaseModel):
    """成交数据"""
    trade_id: str
    price: str
    size: str
    side: str
    timestamp: str

class OKXCandle(BaseModel):
    """K线数据"""
    timestamp: str
    open: str
    high: str
    low: str
    close: str
    volume: str
```

### 6.3 通用响应包装

```python
class OKXResponse(BaseModel):
    """OKX API通用响应"""
    mode: str  # live/demo
    data: Any
    timestamp: str
```

## 7. 错误处理

### 7.1 错误类型定义

**文件位置：** `app/okx/exceptions.py`

```python
class OKXError(Exception):
    """OKX API错误基类"""
    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class OKXAuthError(OKXError):
    """认证错误（API密钥无效、签名错误等）"""
    pass

class OKXRateLimitError(OKXError):
    """频率限制错误"""
    pass

class OKXInsufficientBalanceError(OKXError):
    """余额不足错误"""
    pass

class OKXOrderError(OKXError):
    """订单相关错误（下单失败、撤单失败等）"""
    pass

class OKXConfigError(OKXError):
    """配置错误（缺少API密钥等）"""
    pass
```

### 7.2 错误响应格式

```python
class OKXErrorResponse(BaseModel):
    """错误响应"""
    error_code: str
    error_message: str
    mode: str
    timestamp: str
```

### 7.3 路由层错误处理

**客户端工厂函数：**

```python
# app/okx/__init__.py
from typing import Dict
from .trading_client import OKXTradingClient
from .exceptions import OKXConfigError
import os

_client_cache: Dict[str, OKXTradingClient] = {}

def get_okx_client(mode: str = "demo") -> OKXTradingClient:
    """获取OKX客户端实例（单例模式）

    Args:
        mode: 模式 (live/demo)

    Returns:
        OKXTradingClient实例

    Raises:
        OKXConfigError: 配置缺失或无效
    """
    if mode not in ["live", "demo"]:
        raise OKXConfigError(f"Invalid mode: {mode}")

    # 检查缓存
    if mode in _client_cache:
        return _client_cache[mode]

    # 读取配置
    prefix = f"OKX_{mode.upper()}_"
    api_key = os.getenv(f"{prefix}API_KEY")
    secret_key = os.getenv(f"{prefix}SECRET_KEY")
    passphrase = os.getenv(f"{prefix}PASSPHRASE")

    if not all([api_key, secret_key, passphrase]):
        raise OKXConfigError(f"Missing OKX {mode} configuration")

    # 创建客户端
    client = OKXTradingClient(
        api_key=api_key,
        secret_key=secret_key,
        passphrase=passphrase,
        is_demo=(mode == "demo")
    )

    # 缓存
    _client_cache[mode] = client
    return client
```

**路由层使用示例：**

```python
from fastapi import HTTPException
from app.okx import get_okx_client

@router.post("/trade/order")
async def place_order(request: OKXOrderRequest, mode: str = "demo"):
    try:
        client = get_okx_client(mode)
        result = await client.place_order(...)
        return result
    except OKXAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except OKXInsufficientBalanceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OKXRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except OKXOrderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### 7.4 HTTP状态码映射

| 状态码 | 错误类型 | 说明 |
|--------|----------|------|
| 400 | Bad Request | 业务错误（余额不足、参数错误、订单错误等） |
| 401 | Unauthorized | 认证错误（API密钥无效、签名错误） |
| 429 | Too Many Requests | 频率限制 |
| 500 | Internal Server Error | 服务器内部错误 |

## 8. 安全考虑

### 8.1 API密钥管理

- **存储方式**: 存储在 `.env` 文件中
- **版本控制**: `.env` 文件不提交到代码仓库（已在 `.gitignore` 中）
- **日志保护**: 日志中不记录完整API密钥和密码
- **环境隔离**: 实盘和模拟盘使用不同的API密钥

### 8.2 实盘/模拟盘隔离

- 所有API请求必须明确指定 `mode` 参数
- 所有API响应中包含 `mode` 字段标识
- 日志中明确标注操作模式 `[OKX-LIVE]` 或 `[OKX-DEMO]`
- 可选：实盘操作需要额外确认机制（未来扩展）

### 8.3 请求验证

- 使用Pydantic模型进行请求参数验证
- 数量、价格等字段进行范围检查
- 防止SQL注入、XSS等常见攻击
- 订单ID、产品ID等参数进行格式验证

### 8.4 日志记录

**日志格式：**
```python
logger.info(f"[OKX-{mode.upper()}] Place order: {inst_id} {side} {size}")
logger.info(f"[OKX-{mode.upper()}] Order result: {order_id} {status}")
logger.warning(f"[OKX-{mode.upper()}] Rate limit hit, retrying...")
logger.error(f"[OKX-{mode.upper()}] Order failed: {error_message}")
```

**日志级别：**
- INFO: 正常操作（下单、撤单、查询等）
- WARNING: 警告信息（频率限制、重试等）
- ERROR: 错误信息（下单失败、认证失败等）

### 8.5 频率限制与重试策略

**OKX API频率限制：**
- 不同接口有不同的频率限制（详见OKX API文档）
- 超过限制会返回429错误

**重试策略：**
```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
async def _call_with_retry(self, func, *args, **kwargs):
    """带重试的API调用

    Args:
        func: 要调用的函数
        *args, **kwargs: 函数参数

    Returns:
        函数返回值

    Raises:
        OKXRateLimitError: 超过重试次数仍然失败
    """
    try:
        return await func(*args, **kwargs)
    except OKXRateLimitError as e:
        logger.warning(f"Rate limit hit, retrying... {e}")
        raise
```

**实现位置**: `app/okx/trading_client.py` 中的私有方法

### 8.6 实盘操作确认机制（未来扩展）

**当前版本**: 不实现额外确认机制，由调用方负责确认

**未来扩展**:
- 可选的实盘操作二次确认
- 实盘操作审计日志
- 实盘操作金额/数量限制

## 9. 测试计划

### 9.1 单元测试

**文件位置：** `tests/test_okx_client.py`

```python
import pytest
from app.okx.trading_client import OKXTradingClient

class TestOKXTradingClient:
    def test_init_demo_client(self):
        """测试模拟盘客户端初始化"""
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )
        assert client.is_demo == True

    def test_init_live_client(self):
        """测试实盘客户端初始化"""
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=False
        )
        assert client.is_demo == False

    @pytest.mark.asyncio
    async def test_get_balance(self, mock_okx_client):
        """测试获取余额"""
        result = await mock_okx_client.get_account_balance()
        assert "balances" in result

    @pytest.mark.asyncio
    async def test_place_order(self, mock_okx_client):
        """测试下单"""
        result = await mock_okx_client.place_order(
            inst_id="BTC-USDT",
            side="buy",
            order_type="limit",
            size="0.01",
            price="50000"
        )
        assert "order_id" in result
```

### 9.2 集成测试

**文件位置：** `tests/test_okx_routes.py`

```python
import pytest
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)

class TestOKXRoutes:
    def test_get_balance_endpoint(self):
        """测试余额查询接口"""
        response = client.get("/api/okx/account/balance?mode=demo")
        assert response.status_code == 200
        assert "balances" in response.json()

    def test_place_order_endpoint(self):
        """测试下单接口"""
        response = client.post(
            "/api/okx/trade/order?mode=demo",
            json={
                "inst_id": "BTC-USDT",
                "side": "buy",
                "order_type": "limit",
                "size": "0.01",
                "price": "50000"
            }
        )
        assert response.status_code == 200
        assert "order_id" in response.json()

    def test_invalid_credentials(self):
        """测试无效凭证"""
        # 临时设置无效的API密钥
        import os
        original_key = os.getenv("OKX_DEMO_API_KEY")
        os.environ["OKX_DEMO_API_KEY"] = "invalid_key"

        response = client.get("/api/okx/account/balance?mode=demo")
        assert response.status_code == 401

        # 恢复原始密钥
        os.environ["OKX_DEMO_API_KEY"] = original_key

    def test_mode_switching(self):
        """测试模式切换"""
        # 测试demo模式
        response_demo = client.get("/api/okx/account/balance?mode=demo")
        assert response_demo.status_code == 200
        assert response_demo.json()["mode"] == "demo"

        # 测试live模式（如果配置了实盘API）
        response_live = client.get("/api/okx/account/balance?mode=live")
        # 根据是否配置实盘API，可能返回200或401
        assert response_live.status_code in [200, 401]
```

### 9.3 测试环境

- **优先使用模拟盘**: 所有测试默认使用模拟盘API
- **Pytest fixtures**: 使用fixtures管理测试配置和Mock对象
- **Mock OKX SDK**: 单元测试中Mock OKX SDK响应，避免真实API调用
- **集成测试**: 使用真实模拟盘API进行集成测试

## 10. 部署说明

### 10.1 依赖安装

使用 `uv` 添加OKX SDK依赖：

```bash
cd /home/wcqqq21/finance-agent

# 推荐：使用 python-okx
uv add python-okx

# 或者使用 okx 包（备选）
# uv add okx
```

**注意**: 本设计文档基于 `python-okx` 包。如果使用其他包，需要根据其API文档调整实现细节。

### 10.2 环境配置

编辑 `.env` 文件，添加OKX API配置：

```bash
# OKX Live Trading API (实盘)
OKX_LIVE_API_KEY=your-live-api-key
OKX_LIVE_SECRET_KEY=your-live-secret-key
OKX_LIVE_PASSPHRASE=your-live-passphrase

# OKX Demo Trading API (模拟盘)
OKX_DEMO_API_KEY=923cc63f-d44d-4726-9767-c2237538a36e
OKX_DEMO_SECRET_KEY=5C45AEA155CD0A29B91C26B510D95AB9
OKX_DEMO_PASSPHRASE=200312142058Wcq.

# Default mode: live or demo
OKX_DEFAULT_MODE=demo
```

### 10.3 启动流程

启动FastAPI服务器：

```bash
uv run uvicorn app.api.main:app --port 8080 --reload
```

访问API文档：
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

### 10.4 验证部署

测试模拟盘连接：

```bash
# 获取余额
curl "http://localhost:8080/api/okx/account/balance?mode=demo"

# 获取BTC-USDT行情
curl "http://localhost:8080/api/okx/market/ticker/BTC-USDT?mode=demo"
```

## 11. 使用示例

### 11.1 获取账户余额

```bash
curl "http://localhost:8080/api/okx/account/balance?mode=demo"
```

**响应：**
```json
{
  "mode": "demo",
  "balances": [
    {
      "currency": "USDT",
      "available": "10000.5",
      "frozen": "100.0",
      "total": "10100.5"
    }
  ]
}
```

### 11.2 下市价单

```bash
curl -X POST "http://localhost:8080/api/okx/trade/order?mode=demo" \
  -H "Content-Type: application/json" \
  -d '{
    "inst_id": "BTC-USDT",
    "side": "buy",
    "order_type": "market",
    "size": "0.01"
  }'
```

### 11.3 下限价单

```bash
curl -X POST "http://localhost:8080/api/okx/trade/order?mode=demo" \
  -H "Content-Type: application/json" \
  -d '{
    "inst_id": "BTC-USDT",
    "side": "buy",
    "order_type": "limit",
    "size": "0.01",
    "price": "50000"
  }'
```

### 11.4 撤单

```bash
curl -X DELETE "http://localhost:8080/api/okx/trade/order?mode=demo&inst_id=BTC-USDT&order_id=123456789"
```

### 11.5 查询订单

```bash
curl "http://localhost:8080/api/okx/trade/order/123456789?mode=demo&inst_id=BTC-USDT"
```

### 11.6 查询行情

```bash
# 单个产品ticker
curl "http://localhost:8080/api/okx/market/ticker/BTC-USDT?mode=demo"

# 多个产品ticker
curl "http://localhost:8080/api/okx/market/tickers?mode=demo&inst_type=SPOT"

# 盘口数据
curl "http://localhost:8080/api/okx/market/orderbook/BTC-USDT?mode=demo&depth=20"

# K线数据
curl "http://localhost:8080/api/okx/market/candles/BTC-USDT?mode=demo&bar=1m&limit=100"
```

### 11.7 前端设置管理

```bash
# 获取OKX配置
curl "http://localhost:8080/api/settings/okx?mode=demo"

# 更新OKX配置
curl -X PUT "http://localhost:8080/api/settings/okx" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "demo",
    "api_key": "new-api-key",
    "secret_key": "new-secret-key",
    "passphrase": "new-passphrase"
  }'
```

## 12. 实现优先级

### Phase 1 - 核心功能（MVP）

**目标**: 实现基础交易功能

**任务列表**:
1. 创建 `app/okx/trading_client.py` - OKXTradingClient类
2. 实现账户余额查询 `get_account_balance()`
3. 实现持仓查询 `get_positions()`
4. 实现基础下单功能 `place_order()` (市价单、限价单)
5. 实现撤单功能 `cancel_order()`
6. 实现订单查询 `get_order_details()`, `get_order_list()`
7. 创建 `app/api/routes/okx.py` - API路由
8. 扩展 `app/config_manager.py` - 支持OKX配置
9. 扩展 `app/api/routes/settings.py` - 前端设置接口
10. 扩展 `app/api/models/schemas.py` - 数据模型
11. 创建 `app/okx/exceptions.py` - 错误处理
12. 编写单元测试

**预计时间**: 2-3天

### Phase 2 - 行情数据

**目标**: 实现行情数据查询

**任务列表**:
1. 实现Ticker行情 `get_ticker()`, `get_tickers()`
2. 实现盘口数据 `get_orderbook()`
3. 实现最近成交 `get_recent_trades()`
4. 实现K线数据 `get_candlesticks()`
5. 添加对应的API路由
6. 编写集成测试

**预计时间**: 1-2天

### Phase 3 - 高级功能

**目标**: 实现高级交易功能

**任务列表**:
1. 批量下单
2. 改单功能
3. 条件单（止盈止损）
4. 更多订单类型支持

**预计时间**: 2-3天

### Phase 4 - 优化与扩展

**目标**: 性能优化和功能扩展

**任务列表**:
1. 请求缓存机制
2. WebSocket实时推送
3. 性能优化
4. 监控告警
5. 完善文档

**预计时间**: 3-5天

## 13. 参考资料

### 13.1 官方文档

- **OKX API官方文档**: https://www.okx.com/docs-v5/en/
- **OKX REST API**: https://www.okx.com/docs-v5/en/#overview-rest-api
- **OKX 交易API**: https://www.okx.com/docs-v5/en/#order-book-trading-trade
- **OKX 账户API**: https://www.okx.com/docs-v5/en/#trading-account-rest-api
- **OKX 行情API**: https://www.okx.com/docs-v5/en/#order-book-trading-market-data

### 13.2 SDK文档

- **python-okx**: https://pypi.org/project/python-okx/
- **okx (pyted)**: https://pypi.org/project/okx/ 和 https://github.com/pyted/okx
- **其他备选SDK**:
  - okx-sdk: https://pypi.org/project/okx-sdk
  - pyokx: https://pypi.org/project/pyokx/

**注意**: 本设计文档基于 `python-okx` 包。实际实现时需要根据选定SDK的API文档调整代码。

### 13.3 项目内部参考

- **Polymarket集成**: `app/polymarket/client.py`
- **API路由示例**: `app/api/routes/stocks.py`
- **配置管理**: `app/config_manager.py`
- **数据模型**: `app/api/models/schemas.py`

### 13.4 相关工具

- **OKX MCP Server**: `okx-trade-mcp` (npm包)
- **OKX CLI工具**: `okx-trade-cli` (npm包)

---

## 附录A: 文件清单

### 新增文件

```
app/okx/
├── __init__.py                 # 模块初始化
├── trading_client.py           # OKX交易客户端
└── exceptions.py               # 错误定义

tests/
├── test_okx_client.py          # 客户端单元测试
└── test_okx_routes.py          # 路由集成测试
```

### 修改文件

```
app/api/routes/
├── okx.py                      # 新增OKX路由
└── settings.py                 # 扩展设置接口

app/api/models/
└── schemas.py                  # 扩展数据模型

app/
├── config_manager.py           # 扩展配置管理
└── api/main.py                 # 注册OKX路由

.env                            # 添加OKX配置
pyproject.toml                  # 添加okx依赖
```

## 附录B: API端点汇总

### 账户管理
- `GET /api/okx/account/balance`
- `GET /api/okx/account/positions`
- `GET /api/okx/account/config`

### 交易管理
- `POST /api/okx/trade/order`
- `DELETE /api/okx/trade/order`
- `GET /api/okx/trade/order/{order_id}`
- `GET /api/okx/trade/orders`

### 行情数据
- `GET /api/okx/market/ticker/{inst_id}`
- `GET /api/okx/market/tickers`
- `GET /api/okx/market/orderbook/{inst_id}`
- `GET /api/okx/market/trades/{inst_id}`
- `GET /api/okx/market/candles/{inst_id}`

### 系统管理
- `GET /api/okx/system/mode`
- `POST /api/okx/system/mode`

### 设置管理
- `GET /api/settings/okx`
- `PUT /api/settings/okx`

---

**文档版本**: 1.0
**创建日期**: 2026-03-20
**最后更新**: 2026-03-20
**作者**: Finance Agent Team
