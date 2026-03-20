# OKX集成 - Phase 2: 客户端API层（Task 6-9）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现OKXTradingClient的核心API功能，包括账户管理（余额、持仓）和交易执行（下单、撤单、订单查询）

**Prerequisites:** Phase 1（Task 1-5）已完成

**Architecture:** 使用asyncio.to_thread()将同步SDK调用包装为异步接口，不阻塞FastAPI事件循环

**Tech Stack:** python-okx SDK, asyncio, tenacity (重试机制)

---

## 实现策略

### 异步包装模式

所有API方法采用统一的异步包装模式：

```python
async def public_method(self, ...):
    """公开的异步接口"""
    return await asyncio.to_thread(self._method_sync, ...)

def _method_sync(self, ...):
    """私有的同步实现，调用SDK"""
    response = self.sdk_api.method(...)
    self._validate_response(response)
    return self._parse_response(response)
```

### 错误处理流程

```python
def _validate_response(self, response: Dict) -> None:
    """验证OKX API响应"""
    code = response.get('code')
    if code != '0':
        msg = response.get('msg', 'Unknown error')
        
        # 错误码映射
        if code in ['50113', '50101', '50102']:
            raise OKXAuthError(msg, code=code)
        elif code == '50011':
            raise OKXRateLimitError(msg, code=code)
        elif code.startswith('51'):
            # 业务错误
            if '余额不足' in msg or 'Insufficient' in msg:
                raise OKXInsufficientBalanceError(msg, code=code)
            else:
                raise OKXOrderError(msg, code=code)
        else:
            raise OKXError(msg, code=code)
```

---

## Task 6: 账户余额查询API

**Files:**
- Modify: `app/okx/trading_client.py`
- Create: `tests/test_okx_client_balance.py`

### Step 1: 编写余额查询测试

Create `tests/test_okx_client_balance.py`:

```python
"""测试OKXTradingClient账户余额功能"""
import pytest
from unittest.mock import Mock, patch
from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    """创建mock客户端"""
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )
        client.account_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_get_account_balance_all_currencies(mock_client):
    """测试获取所有币种余额"""
    # Mock SDK响应
    mock_client.account_api.get_account_balance = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'details': [
                {'ccy': 'USDT', 'availBal': '1000', 'frozenBal': '100', 'bal': '1100'},
                {'ccy': 'BTC', 'availBal': '0.5', 'frozenBal': '0', 'bal': '0.5'}
            ]
        }]
    })

    result = await mock_client.get_account_balance()

    assert len(result) == 2
    assert result[0]['currency'] == 'USDT'
    assert result[0]['available'] == '1000'
    assert result[0]['frozen'] == '100'
    assert result[0]['total'] == '1100'
    assert result[1]['currency'] == 'BTC'


@pytest.mark.asyncio
async def test_get_account_balance_single_currency(mock_client):
    """测试获取单个币种余额"""
    mock_client.account_api.get_account_balance = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'details': [
                {'ccy': 'USDT', 'availBal': '1000', 'frozenBal': '100', 'bal': '1100'}
            ]
        }]
    })

    result = await mock_client.get_account_balance(currency='USDT')

    assert len(result) == 1
    assert result[0]['currency'] == 'USDT'
    mock_client.account_api.get_account_balance.assert_called_once_with(ccy='USDT')


@pytest.mark.asyncio
async def test_get_account_balance_error(mock_client):
    """测试余额查询错误处理"""
    from app.okx.exceptions import OKXAuthError
    
    mock_client.account_api.get_account_balance = Mock(return_value={
        'code': '50113',
        'msg': 'Invalid Sign'
    })

    with pytest.raises(OKXAuthError) as exc_info:
        await mock_client.get_account_balance()
    
    assert exc_info.value.code == '50113'
    assert 'Invalid Sign' in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_account_balance_empty(mock_client):
    """测试空余额响应"""
    mock_client.account_api.get_account_balance = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{'details': []}]
    })

    result = await mock_client.get_account_balance()
    assert result == []
```

### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_client_balance.py -v
```

Expected: 测试失败，提示方法不存在

### Step 3: 实现余额查询方法

在 `app/okx/trading_client.py` 中添加：

```python
import asyncio
from typing import Dict, List, Optional

# 在类中添加以下方法

async def get_account_balance(self, currency: Optional[str] = None) -> List[Dict]:
    """获取账户余额（异步）

    Args:
        currency: 币种，如BTC、USDT，不传则返回所有币种

    Returns:
        余额信息列表，格式：
        [
            {
                "currency": "USDT",
                "available": "1000.5",
                "frozen": "100.0",
                "total": "1100.5"
            }
        ]

    Raises:
        OKXAuthError: 认证错误
        OKXError: 其他API错误
    """
    return await asyncio.to_thread(self._get_account_balance_sync, currency)

def _get_account_balance_sync(self, currency: Optional[str] = None) -> List[Dict]:
    """获取账户余额的同步实现"""
    # 构建请求参数
    params = {}
    if currency:
        params['ccy'] = currency

    # 调用SDK
    response = self.account_api.get_account_balance(**params)

    # 验证响应
    self._validate_response(response)

    # 解析余额数据
    balances = []
    data = response.get('data', [])
    if data and len(data) > 0:
        details = data[0].get('details', [])
        for detail in details:
            balances.append({
                'currency': detail.get('ccy'),
                'available': detail.get('availBal'),
                'frozen': detail.get('frozenBal'),
                'total': detail.get('bal')
            })

    return balances

def _validate_response(self, response: Dict) -> None:
    """验证OKX API响应
    
    Args:
        response: OKX API响应
        
    Raises:
        OKXAuthError: 认证错误
        OKXRateLimitError: 频率限制错误
        OKXError: 其他错误
    """
    from .exceptions import (
        OKXError, OKXAuthError, OKXRateLimitError,
        OKXInsufficientBalanceError, OKXOrderError
    )
    
    code = response.get('code')
    if code != '0':
        msg = response.get('msg', 'Unknown error')
        
        # 认证错误
        if code in ['50113', '50101', '50102', '50103']:
            raise OKXAuthError(msg, code=code)
        # 频率限制
        elif code == '50011':
            raise OKXRateLimitError(msg, code=code)
        # 业务错误
        elif code and code.startswith('51'):
            if '余额不足' in msg or 'Insufficient' in msg.lower():
                raise OKXInsufficientBalanceError(msg, code=code)
            else:
                raise OKXOrderError(msg, code=code)
        else:
            raise OKXError(msg, code=code)
```


### Step 4: 运行测试验证

```bash
uv run pytest tests/test_okx_client_balance.py -v
```

Expected: 所有测试通过

### Step 5: 提交余额查询功能

```bash
git add app/okx/trading_client.py tests/test_okx_client_balance.py
git commit -m "feat(okx): add account balance query API"
```

---

## Task 7: 持仓查询API

**Files:**
- Modify: `app/okx/trading_client.py`
- Create: `tests/test_okx_client_positions.py`

### Step 1: 编写持仓查询测试

Create `tests/test_okx_client_positions.py`:

```python
"""测试OKXTradingClient持仓功能"""
import pytest
from unittest.mock import Mock, patch
from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )
        client.account_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_get_positions_all(mock_client):
    """测试获取所有持仓"""
    mock_client.account_api.get_positions = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [
            {
                'instId': 'BTC-USDT-SWAP',
                'posSide': 'long',
                'pos': '10',
                'availPos': '10',
                'avgPx': '50000',
                'upl': '500',
                'lever': '10'
            },
            {
                'instId': 'ETH-USDT-SWAP',
                'posSide': 'short',
                'pos': '20',
                'availPos': '20',
                'avgPx': '3000',
                'upl': '-100',
                'lever': '5'
            }
        ]
    })

    result = await mock_client.get_positions()

    assert len(result) == 2
    assert result[0]['inst_id'] == 'BTC-USDT-SWAP'
    assert result[0]['position_side'] == 'long'
    assert result[0]['position'] == '10'
    assert result[0]['average_price'] == '50000'
    assert result[1]['inst_id'] == 'ETH-USDT-SWAP'


@pytest.mark.asyncio
async def test_get_positions_by_inst_type(mock_client):
    """测试按产品类型获取持仓"""
    mock_client.account_api.get_positions = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'instId': 'BTC-USDT',
            'posSide': 'net',
            'pos': '0.5',
            'availPos': '0.5',
            'avgPx': '50000',
            'upl': '0',
            'lever': '1'
        }]
    })

    result = await mock_client.get_positions(inst_type='SPOT')

    assert len(result) == 1
    assert result[0]['inst_id'] == 'BTC-USDT'
    mock_client.account_api.get_positions.assert_called_once_with(instType='SPOT')


@pytest.mark.asyncio
async def test_get_positions_empty(mock_client):
    """测试空持仓"""
    mock_client.account_api.get_positions = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': []
    })

    result = await mock_client.get_positions()
    assert result == []


@pytest.mark.asyncio
async def test_get_positions_error(mock_client):
    """测试持仓查询错误"""
    from app.okx.exceptions import OKXAuthError
    
    mock_client.account_api.get_positions = Mock(return_value={
        'code': '50113',
        'msg': 'Invalid Sign'
    })

    with pytest.raises(OKXAuthError):
        await mock_client.get_positions()
```

### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_client_positions.py -v
```

### Step 3: 实现持仓查询方法

在 `app/okx/trading_client.py` 中添加：

```python
async def get_positions(self, inst_type: Optional[str] = None) -> List[Dict]:
    """获取持仓信息（异步）

    Args:
        inst_type: 产品类型，如SPOT/MARGIN/SWAP/FUTURES/OPTION
                  不传则返回所有类型

    Returns:
        持仓列表，格式：
        [
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

    Raises:
        OKXAuthError: 认证错误
        OKXError: 其他API错误
    """
    return await asyncio.to_thread(self._get_positions_sync, inst_type)

def _get_positions_sync(self, inst_type: Optional[str] = None) -> List[Dict]:
    """获取持仓的同步实现"""
    # 构建请求参数
    params = {}
    if inst_type:
        params['instType'] = inst_type

    # 调用SDK
    response = self.account_api.get_positions(**params)

    # 验证响应
    self._validate_response(response)

    # 解析持仓数据
    positions = []
    for pos in response.get('data', []):
        positions.append({
            'inst_id': pos.get('instId'),
            'position_side': pos.get('posSide'),
            'position': pos.get('pos'),
            'available_position': pos.get('availPos'),
            'average_price': pos.get('avgPx'),
            'unrealized_pnl': pos.get('upl'),
            'leverage': pos.get('lever')
        })

    return positions
```

### Step 4: 运行测试验证

```bash
uv run pytest tests/test_okx_client_positions.py -v
```

Expected: 所有测试通过

### Step 5: 提交持仓查询功能

```bash
git add app/okx/trading_client.py tests/test_okx_client_positions.py
git commit -m "feat(okx): add positions query API"
```

---

## Task 8: 下单API

**Files:**
- Modify: `app/okx/trading_client.py`
- Create: `tests/test_okx_client_order.py`

### Step 1: 编写下单测试

Create `tests/test_okx_client_order.py`:

```python
"""测试OKXTradingClient下单功能"""
import pytest
from unittest.mock import Mock, patch
from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )
        client.trade_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_place_limit_order(mock_client):
    """测试限价单"""
    mock_client.trade_api.place_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123456',
            'clOrdId': 'my-order-1',
            'sCode': '0',
            'sMsg': ''
        }]
    })

    result = await mock_client.place_order(
        inst_id='BTC-USDT',
        side='buy',
        order_type='limit',
        size='0.01',
        price='50000'
    )

    assert result['order_id'] == '123456'
    assert result['client_order_id'] == 'my-order-1'
    assert result['status_code'] == '0'
    
    # 验证SDK调用参数
    mock_client.trade_api.place_order.assert_called_once()
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert call_kwargs['instId'] == 'BTC-USDT'
    assert call_kwargs['side'] == 'buy'
    assert call_kwargs['ordType'] == 'limit'
    assert call_kwargs['sz'] == '0.01'
    assert call_kwargs['px'] == '50000'
    assert call_kwargs['tdMode'] == 'cash'


@pytest.mark.asyncio
async def test_place_market_order(mock_client):
    """测试市价单"""
    mock_client.trade_api.place_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123457',
            'clOrdId': '',
            'sCode': '0',
            'sMsg': ''
        }]
    })

    result = await mock_client.place_order(
        inst_id='BTC-USDT',
        side='sell',
        order_type='market',
        size='0.01'
    )

    assert result['order_id'] == '123457'
    
    # 市价单不应该传price
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert 'px' not in call_kwargs


@pytest.mark.asyncio
async def test_place_order_with_client_order_id(mock_client):
    """测试带客户端订单ID的下单"""
    mock_client.trade_api.place_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123458',
            'clOrdId': 'custom-id-123',
            'sCode': '0',
            'sMsg': ''
        }]
    })

    result = await mock_client.place_order(
        inst_id='ETH-USDT',
        side='buy',
        order_type='limit',
        size='1',
        price='3000',
        client_order_id='custom-id-123'
    )

    assert result['client_order_id'] == 'custom-id-123'
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert call_kwargs['clOrdId'] == 'custom-id-123'


@pytest.mark.asyncio
async def test_place_order_insufficient_balance(mock_client):
    """测试余额不足错误"""
    from app.okx.exceptions import OKXInsufficientBalanceError
    
    mock_client.trade_api.place_order = Mock(return_value={
        'code': '51008',
        'msg': 'Insufficient balance'
    })

    with pytest.raises(OKXInsufficientBalanceError) as exc_info:
        await mock_client.place_order(
            inst_id='BTC-USDT',
            side='buy',
            order_type='market',
            size='100'
        )
    
    assert exc_info.value.code == '51008'


@pytest.mark.asyncio
async def test_place_order_error(mock_client):
    """测试下单错误"""
    from app.okx.exceptions import OKXOrderError
    
    mock_client.trade_api.place_order = Mock(return_value={
        'code': '51000',
        'msg': 'Order placement failed'
    })

    with pytest.raises(OKXOrderError):
        await mock_client.place_order(
            inst_id='BTC-USDT',
            side='buy',
            order_type='limit',
            size='0.01',
            price='50000'
        )
```


### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_client_order.py -v
```

### Step 3: 实现下单方法

在 `app/okx/trading_client.py` 中添加：

```python
async def place_order(
    self,
    inst_id: str,
    side: str,
    order_type: str,
    size: str,
    price: Optional[str] = None,
    client_order_id: Optional[str] = None,
    **kwargs
) -> Dict:
    """下单（异步）

    Args:
        inst_id: 产品ID，如 BTC-USDT
        side: 订单方向 buy/sell
        order_type: 订单类型 market/limit/post_only/fok/ioc
        size: 委托数量
        price: 委托价格（限价单必填）
        client_order_id: 客户端订单ID（可选）
        **kwargs: 其他参数（如reduce_only等）

    Returns:
        订单信息，格式：
        {
            "order_id": "123456",
            "client_order_id": "my-order-1",
            "status_code": "0"
        }

    Raises:
        OKXAuthError: 认证错误
        OKXInsufficientBalanceError: 余额不足
        OKXOrderError: 订单错误
        OKXError: 其他错误
    """
    return await asyncio.to_thread(
        self._place_order_sync, inst_id, side, order_type, size, price, client_order_id, **kwargs
    )

def _place_order_sync(
    self,
    inst_id: str,
    side: str,
    order_type: str,
    size: str,
    price: Optional[str] = None,
    client_order_id: Optional[str] = None,
    **kwargs
) -> Dict:
    """下单的同步实现"""
    # 构建请求参数
    params = {
        'instId': inst_id,
        'tdMode': 'cash',  # 现货交易模式
        'side': side,
        'ordType': order_type,
        'sz': size
    }

    # 限价单需要价格
    if price:
        params['px'] = price

    # 客户端订单ID
    if client_order_id:
        params['clOrdId'] = client_order_id

    # 其他参数
    params.update(kwargs)

    # 调用SDK
    response = self.trade_api.place_order(**params)

    # 验证响应
    self._validate_response(response)

    # 解析订单数据
    data = response.get('data', [{}])[0]
    return {
        'order_id': data.get('ordId'),
        'client_order_id': data.get('clOrdId', ''),
        'status_code': data.get('sCode', '0')
    }
```

### Step 4: 运行测试验证

```bash
uv run pytest tests/test_okx_client_order.py -v
```

Expected: 所有测试通过

### Step 5: 提交下单功能

```bash
git add app/okx/trading_client.py tests/test_okx_client_order.py
git commit -m "feat(okx): add place order API"
```

---

## Task 9: 撤单和订单查询API

**Files:**
- Modify: `app/okx/trading_client.py`
- Create: `tests/test_okx_client_order_mgmt.py`

### Step 1: 编写订单管理测试

Create `tests/test_okx_client_order_mgmt.py`:

```python
"""测试订单管理功能"""
import pytest
from unittest.mock import Mock, patch
from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )
        client.trade_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_cancel_order(mock_client):
    """测试撤单"""
    mock_client.trade_api.cancel_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123456',
            'clOrdId': '',
            'sCode': '0',
            'sMsg': ''
        }]
    })

    result = await mock_client.cancel_order(
        inst_id='BTC-USDT',
        order_id='123456'
    )

    assert result['order_id'] == '123456'
    assert result['status_code'] == '0'
    
    # 验证SDK调用
    mock_client.trade_api.cancel_order.assert_called_once()
    call_kwargs = mock_client.trade_api.cancel_order.call_args[1]
    assert call_kwargs['instId'] == 'BTC-USDT'
    assert call_kwargs['ordId'] == '123456'


@pytest.mark.asyncio
async def test_cancel_order_by_client_order_id(mock_client):
    """测试通过客户端订单ID撤单"""
    mock_client.trade_api.cancel_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123456',
            'clOrdId': 'my-order-1',
            'sCode': '0',
            'sMsg': ''
        }]
    })

    result = await mock_client.cancel_order(
        inst_id='BTC-USDT',
        client_order_id='my-order-1'
    )

    assert result['order_id'] == '123456'
    call_kwargs = mock_client.trade_api.cancel_order.call_args[1]
    assert call_kwargs['clOrdId'] == 'my-order-1'


@pytest.mark.asyncio
async def test_cancel_order_not_found(mock_client):
    """测试撤单失败（订单不存在）"""
    from app.okx.exceptions import OKXOrderError
    
    mock_client.trade_api.cancel_order = Mock(return_value={
        'code': '51400',
        'msg': 'Order does not exist'
    })

    with pytest.raises(OKXOrderError) as exc_info:
        await mock_client.cancel_order(
            inst_id='BTC-USDT',
            order_id='999999'
        )
    
    assert exc_info.value.code == '51400'


@pytest.mark.asyncio
async def test_get_order_details(mock_client):
    """测试查询订单详情"""
    mock_client.trade_api.get_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123456',
            'clOrdId': 'my-order-1',
            'instId': 'BTC-USDT',
            'state': 'filled',
            'side': 'buy',
            'ordType': 'limit',
            'sz': '0.01',
            'fillSz': '0.01',
            'px': '50000',
            'avgPx': '50000',
            'cTime': '1710000000000'
        }]
    })

    result = await mock_client.get_order_details(
        inst_id='BTC-USDT',
        order_id='123456'
    )

    assert result['order_id'] == '123456'
    assert result['inst_id'] == 'BTC-USDT'
    assert result['status'] == 'filled'
    assert result['side'] == 'buy'
    assert result['order_type'] == 'limit'
    assert result['size'] == '0.01'
    assert result['filled_size'] == '0.01'
    assert result['price'] == '50000'
    assert result['average_price'] == '50000'


@pytest.mark.asyncio
async def test_get_order_details_by_client_order_id(mock_client):
    """测试通过客户端订单ID查询"""
    mock_client.trade_api.get_order = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [{
            'ordId': '123456',
            'clOrdId': 'my-order-1',
            'instId': 'BTC-USDT',
            'state': 'live',
            'side': 'buy',
            'ordType': 'limit',
            'sz': '0.01',
            'fillSz': '0',
            'px': '50000',
            'avgPx': '',
            'cTime': '1710000000000'
        }]
    })

    result = await mock_client.get_order_details(
        inst_id='BTC-USDT',
        client_order_id='my-order-1'
    )

    assert result['client_order_id'] == 'my-order-1'
    assert result['status'] == 'live'
    assert result['filled_size'] == '0'
    assert result['average_price'] is None


@pytest.mark.asyncio
async def test_get_order_history(mock_client):
    """测试查询历史订单"""
    mock_client.trade_api.get_orders_history = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': [
            {
                'ordId': '123456',
                'clOrdId': '',
                'instId': 'BTC-USDT',
                'state': 'filled',
                'side': 'buy',
                'ordType': 'market',
                'sz': '0.01',
                'fillSz': '0.01',
                'px': '',
                'avgPx': '50000',
                'cTime': '1710000000000'
            },
            {
                'ordId': '123457',
                'clOrdId': '',
                'instId': 'ETH-USDT',
                'state': 'canceled',
                'side': 'sell',
                'ordType': 'limit',
                'sz': '1',
                'fillSz': '0',
                'px': '3000',
                'avgPx': '',
                'cTime': '1710000100000'
            }
        ]
    })

    result = await mock_client.get_order_history(inst_type='SPOT', limit=10)

    assert len(result) == 2
    assert result[0]['order_id'] == '123456'
    assert result[0]['status'] == 'filled'
    assert result[1]['order_id'] == '123457'
    assert result[1]['status'] == 'canceled'
    
    # 验证SDK调用
    call_kwargs = mock_client.trade_api.get_orders_history.call_args[1]
    assert call_kwargs['instType'] == 'SPOT'
    assert call_kwargs['limit'] == '10'


@pytest.mark.asyncio
async def test_get_order_history_empty(mock_client):
    """测试空历史订单"""
    mock_client.trade_api.get_orders_history = Mock(return_value={
        'code': '0',
        'msg': '',
        'data': []
    })

    result = await mock_client.get_order_history(inst_type='SPOT')
    assert result == []
```


### Step 2: 运行测试确认失败

```bash
uv run pytest tests/test_okx_client_order_mgmt.py -v
```

### Step 3: 实现订单管理方法

在 `app/okx/trading_client.py` 中添加：

```python
async def cancel_order(
    self,
    inst_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Dict:
    """撤单（异步）

    Args:
        inst_id: 产品ID
        order_id: 订单ID（与client_order_id二选一）
        client_order_id: 客户端订单ID（与order_id二选一）

    Returns:
        撤单结果，格式：
        {
            "order_id": "123456",
            "client_order_id": "my-order-1",
            "status_code": "0"
        }

    Raises:
        ValueError: 如果order_id和client_order_id都未提供
        OKXOrderError: 订单不存在或撤单失败
        OKXError: 其他错误
    """
    if not order_id and not client_order_id:
        raise ValueError("Either order_id or client_order_id must be provided")
    
    return await asyncio.to_thread(
        self._cancel_order_sync, inst_id, order_id, client_order_id
    )

def _cancel_order_sync(
    self,
    inst_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Dict:
    """撤单的同步实现"""
    # 构建请求参数
    params = {'instId': inst_id}
    
    if order_id:
        params['ordId'] = order_id
    if client_order_id:
        params['clOrdId'] = client_order_id

    # 调用SDK
    response = self.trade_api.cancel_order(**params)

    # 验证响应
    self._validate_response(response)

    # 解析结果
    data = response.get('data', [{}])[0]
    return {
        'order_id': data.get('ordId'),
        'client_order_id': data.get('clOrdId', ''),
        'status_code': data.get('sCode', '0')
    }


async def get_order_details(
    self,
    inst_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Dict:
    """查询订单详情（异步）

    Args:
        inst_id: 产品ID
        order_id: 订单ID（与client_order_id二选一）
        client_order_id: 客户端订单ID（与order_id二选一）

    Returns:
        订单详情，格式：
        {
            "order_id": "123456",
            "client_order_id": "my-order-1",
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

    Raises:
        ValueError: 如果order_id和client_order_id都未提供
        OKXOrderError: 订单不存在
        OKXError: 其他错误
    """
    if not order_id and not client_order_id:
        raise ValueError("Either order_id or client_order_id must be provided")
    
    return await asyncio.to_thread(
        self._get_order_details_sync, inst_id, order_id, client_order_id
    )

def _get_order_details_sync(
    self,
    inst_id: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None
) -> Dict:
    """查询订单详情的同步实现"""
    # 构建请求参数
    params = {'instId': inst_id}
    
    if order_id:
        params['ordId'] = order_id
    if client_order_id:
        params['clOrdId'] = client_order_id

    # 调用SDK
    response = self.trade_api.get_order(**params)

    # 验证响应
    self._validate_response(response)

    # 解析订单数据
    data = response.get('data', [{}])[0]
    return {
        'order_id': data.get('ordId'),
        'client_order_id': data.get('clOrdId', ''),
        'inst_id': data.get('instId'),
        'status': data.get('state'),
        'side': data.get('side'),
        'order_type': data.get('ordType'),
        'size': data.get('sz'),
        'filled_size': data.get('fillSz'),
        'price': data.get('px') or None,
        'average_price': data.get('avgPx') or None,
        'timestamp': data.get('cTime')
    }


async def get_order_history(
    self,
    inst_type: str = 'SPOT',
    inst_id: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """查询历史订单（异步）

    Args:
        inst_type: 产品类型，如SPOT/MARGIN/SWAP/FUTURES
        inst_id: 产品ID（可选，不传则返回该类型所有产品）
        limit: 返回数量限制，默认100

    Returns:
        历史订单列表，格式同get_order_details

    Raises:
        OKXError: API错误
    """
    return await asyncio.to_thread(
        self._get_order_history_sync, inst_type, inst_id, limit
    )

def _get_order_history_sync(
    self,
    inst_type: str = 'SPOT',
    inst_id: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """查询历史订单的同步实现"""
    # 构建请求参数
    params = {
        'instType': inst_type,
        'limit': str(limit)
    }
    
    if inst_id:
        params['instId'] = inst_id

    # 调用SDK
    response = self.trade_api.get_orders_history(**params)

    # 验证响应
    self._validate_response(response)

    # 解析订单列表
    orders = []
    for order in response.get('data', []):
        orders.append({
            'order_id': order.get('ordId'),
            'client_order_id': order.get('clOrdId', ''),
            'inst_id': order.get('instId'),
            'status': order.get('state'),
            'side': order.get('side'),
            'order_type': order.get('ordType'),
            'size': order.get('sz'),
            'filled_size': order.get('fillSz'),
            'price': order.get('px') or None,
            'average_price': order.get('avgPx') or None,
            'timestamp': order.get('cTime')
        })

    return orders
```

### Step 4: 运行测试验证

```bash
uv run pytest tests/test_okx_client_order_mgmt.py -v
```

Expected: 所有测试通过

### Step 5: 提交订单管理功能

```bash
git add app/okx/trading_client.py tests/test_okx_client_order_mgmt.py
git commit -m "feat(okx): add cancel order and order query APIs"
```

---

## Phase 2 完成标准

- [ ] Task 6: 账户余额查询API ✅
- [ ] Task 7: 持仓查询API ✅
- [ ] Task 8: 下单API ✅
- [ ] Task 9: 撤单和订单查询API ✅

**完成后：** 进入Phase 3（Task 10-12：路由层和集成测试）

---

## 验收标准

1. 所有单元测试通过（覆盖率 ≥ 90%）
2. 异步包装正确实现，不阻塞事件循环
3. 错误处理完善，错误码正确映射
4. 数据格式标准化（驼峰 → 蛇形）
5. 重试机制对频率限制生效

---

## 测试运行

运行所有Phase 2测试：

```bash
# 运行所有OKX客户端测试
uv run pytest tests/test_okx_client*.py -v

# 查看测试覆盖率
uv run pytest tests/test_okx_client*.py --cov=app/okx --cov-report=term-missing
```

---

## 依赖关系

```
Task 5 (客户端初始化)
  ↓
Task 6 (余额查询) ← Task 7 (持仓查询)
  ↓                    ↓
Task 8 (下单) ← Task 9 (撤单和查询)
```

**关键路径：** Task 5 → Task 6 → Task 8 → Task 9

---

## 实现注意事项

### 1. 异步包装

所有方法都使用`asyncio.to_thread()`包装同步SDK调用：
- 公开方法：`async def method(...)`
- 私有实现：`def _method_sync(...)`

### 2. 错误处理

每个SDK调用后都要调用`_validate_response()`验证响应码。

### 3. 数据转换

OKX API使用驼峰命名，返回给调用者时转换为蛇形命名：
- `instId` → `inst_id`
- `ordType` → `order_type`
- `availBal` → `available`

### 4. 可选参数处理

- 限价单必须提供`price`，市价单不需要
- 订单查询可以使用`order_id`或`client_order_id`
- 空字符串转换为`None`（如`avgPx`为空时）

### 5. 日志记录

关键操作添加日志：
```python
logger.info(f"[OKX-{'DEMO' if self.is_demo else 'LIVE'}] Placing order: {inst_id} {side} {size}")
logger.warning(f"[OKX] Rate limit hit, retrying...")
logger.error(f"[OKX] Order failed: {error_msg}")
```

