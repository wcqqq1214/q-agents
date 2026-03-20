# OKX Trading Client 设计文档

**日期：** 2026-03-21  
**状态：** 已批准  
**目标：** 集成OKX交易所API，支持实盘和模拟盘的账户管理、交易执行和行情查询功能

---

## 1. 项目概述

### 1.1 背景

Finance Agent需要集成OKX交易所API，为用户提供加密货币交易功能。OKX提供了独立的实盘和模拟盘环境，需要支持两种模式的无缝切换。

### 1.2 目标

- 封装OKX SDK，提供统一的异步API接口
- 支持实盘（live）和模拟盘（demo）双模式
- 实现账户管理（余额、持仓查询）
- 实现交易执行（下单、撤单、订单查询）
- 提供完善的错误处理和重试机制

### 1.3 范围

**包含：**
- OKXTradingClient核心类实现
- 账户API（余额、持仓）
- 交易API（下单、撤单、订单查询）
- 配置管理和客户端工厂

**不包含：**
- FastAPI路由层（后续Task 10-11实现）
- 前端界面
- 高级交易策略

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────┐
│         FastAPI Routes Layer            │  (Task 10-11)
│    (账户路由 + 交易路由)                  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      OKXTradingClient Layer             │  (Task 5-9)
│  - 异步包装器 (asyncio.to_thread)        │
│  - 错误处理和重试机制                     │
│  - 数据格式标准化                         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         python-okx SDK Layer            │
│  - AccountAPI (同步)                     │
│  - TradeAPI (同步)                       │
│  - MarketAPI (同步)                      │
└─────────────────────────────────────────┘
```


### 2.2 技术栈

- **SDK：** python-okx (v0.4.1)
- **异步框架：** asyncio
- **重试机制：** tenacity
- **数据验证：** Pydantic
- **测试框架：** pytest + pytest-asyncio

### 2.3 关键设计决策

#### 决策1：异步包装策略

**选择方案A：同步SDK + 异步包装器**

**理由：**
1. `python-okx` SDK是同步的，使用`asyncio.to_thread()`包装成异步
2. 不阻塞FastAPI事件循环，保持良好的并发性能
3. 利用现有SDK，避免重新实现签名算法
4. 实现简单，易于维护

**实现方式：**
```python
async def get_account_balance(self, currency: Optional[str] = None):
    """异步获取账户余额"""
    return await asyncio.to_thread(
        self._get_account_balance_sync, currency
    )

def _get_account_balance_sync(self, currency: Optional[str] = None):
    """同步实现，调用SDK"""
    response = self.account_api.get_account_balance(ccy=currency)
    return self._parse_balance_response(response)
```

#### 决策2：凭证管理

**问题：** OKX的实盘和模拟盘使用完全独立的API凭证

**解决方案：**
- 在`.env`中分别存储`OKX_DEMO_*`和`OKX_LIVE_*`凭证
- ConfigManager根据mode参数读取对应凭证
- SDK初始化时根据`is_demo`设置`flag`参数（"1"=模拟盘，"0"=实盘）

#### 决策3：错误处理

**OKX错误码映射：**
- `50113` (Invalid Sign) → `OKXAuthError`
- `50011` (Rate limit) → `OKXRateLimitError`
- `51xxx` (余额/订单错误) → `OKXInsufficientBalanceError` / `OKXOrderError`

**重试策略：**
- 仅对`OKXRateLimitError`进行重试
- 最多重试3次，指数退避（1s, 2s, 4s）
- 认证错误和业务错误直接抛出，不重试

---

## 3. 核心功能模块

### 3.1 客户端初始化 (Task 5)

**功能：** 初始化OKX SDK客户端，支持实盘/模拟盘切换

**实现要点：**
```python
def _init_sdk_clients(self):
    from okx.Account import AccountAPI
    from okx.Trade import TradeAPI
    from okx.MarketData import MarketAPI
    
    flag = "1" if self.is_demo else "0"
    
    self.account_api = AccountAPI(
        api_key=self._api_key,
        api_secret_key=self._secret_key,
        passphrase=self._passphrase,
        flag=flag,
        debug=False
    )
    # Trade API 和 Market API 类似
```


### 3.2 账户管理 (Task 6-7)

#### 3.2.1 获取账户余额

**接口：** `async def get_account_balance(currency: Optional[str] = None) -> List[Dict]`

**参数：**
- `currency`: 币种（如BTC、USDT），不传则返回所有币种

**返回格式：**
```python
[
    {
        "currency": "USDT",
        "available": "1000.5",
        "frozen": "100.0",
        "total": "1100.5"
    }
]
```

**SDK调用：**
```python
response = self.account_api.get_account_balance(ccy=currency)
# response['code'] == '0' 表示成功
# response['data'][0]['details'] 包含余额列表
```

#### 3.2.2 获取持仓信息

**接口：** `async def get_positions(inst_type: Optional[str] = None) -> List[Dict]`

**参数：**
- `inst_type`: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）

**返回格式：**
```python
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
```

### 3.3 交易执行 (Task 8-9)

#### 3.3.1 下单

**接口：** `async def place_order(...) -> Dict`

**参数：**
- `inst_id`: 产品ID（如BTC-USDT）
- `side`: 订单方向（buy/sell）
- `order_type`: 订单类型（market/limit/post_only/fok/ioc）
- `size`: 委托数量
- `price`: 委托价格（限价单必填）
- `client_order_id`: 客户端订单ID（可选）

**返回格式：**
```python
{
    "order_id": "123456",
    "client_order_id": "my-order-1",
    "status_code": "0"
}
```

**SDK调用：**
```python
response = self.trade_api.place_order(
    instId=inst_id,
    tdMode="cash",  # 现货交易模式
    side=side,
    ordType=order_type,
    sz=size,
    px=price  # 限价单需要
)
```

#### 3.3.2 撤单

**接口：** `async def cancel_order(inst_id: str, order_id: str) -> Dict`

**返回格式：**
```python
{
    "order_id": "123456",
    "status_code": "0"
}
```

#### 3.3.3 查询订单详情

**接口：** `async def get_order_details(inst_id: str, order_id: str) -> Dict`

**返回格式：**
```python
{
    "order_id": "123456",
    "inst_id": "BTC-USDT",
    "status": "filled",  # live/partially_filled/filled/canceled
    "side": "buy",
    "order_type": "limit",
    "size": "0.01",
    "filled_size": "0.01",
    "price": "50000",
    "average_price": "50000",
    "timestamp": "2026-03-21T10:00:00Z"
}
```

#### 3.3.4 查询历史订单

**接口：** `async def get_order_history(inst_type: str = "SPOT", ...) -> List[Dict]`

**参数：**
- `inst_type`: 产品类型
- `limit`: 返回数量限制（可选）


---

## 4. 错误处理策略

### 4.1 错误类型定义

已实现的错误类型（`app/okx/exceptions.py`）：

```python
OKXError                    # 基类
├── OKXAuthError           # 认证错误（50113等）
├── OKXRateLimitError      # 频率限制（50011）
├── OKXInsufficientBalanceError  # 余额不足
├── OKXOrderError          # 订单错误
└── OKXConfigError         # 配置错误
```

### 4.2 错误码映射

**认证相关：**
- `50113` - Invalid Sign → `OKXAuthError`
- `50101` - API key invalid → `OKXAuthError`
- `50102` - Timestamp invalid → `OKXAuthError`

**频率限制：**
- `50011` - Rate limit exceeded → `OKXRateLimitError`

**业务错误：**
- `51xxx` - 余额不足、订单错误等 → 根据具体错误码映射

### 4.3 重试机制

使用`tenacity`库实现：

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(OKXRateLimitError),
    reraise=True
)
async def _call_with_retry(self, func, *args, **kwargs):
    """带重试的API调用"""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except OKXRateLimitError as e:
        logger.warning(f"Rate limit hit, retrying... {e}")
        raise
```

**重试策略：**
- 仅对`OKXRateLimitError`重试
- 最多3次，指数退避（1s → 2s → 4s）
- 其他错误直接抛出

### 4.4 响应验证

每个API调用都需要检查响应码：

```python
if response.get('code') != '0':
    error_code = response.get('code')
    error_msg = response.get('msg', 'Unknown error')
    
    # 根据错误码映射到具体异常
    if error_code in ['50113', '50101', '50102']:
        raise OKXAuthError(error_msg, code=error_code)
    elif error_code == '50011':
        raise OKXRateLimitError(error_msg, code=error_code)
    else:
        raise OKXError(error_msg, code=error_code)
```

---

## 5. 数据格式标准化

### 5.1 命名规范

**OKX API → Python：**
- 驼峰命名 → 蛇形命名
- `instId` → `inst_id`
- `ordType` → `order_type`
- `availBal` → `available`

### 5.2 数据类型

**字符串类型：**
- 所有金额、价格、数量使用字符串（避免浮点精度问题）
- 时间戳转换为ISO 8601格式

**示例转换：**
```python
# OKX响应
{
    "instId": "BTC-USDT",
    "availBal": "1000.5",
    "frozenBal": "100.0"
}

# 转换后
{
    "inst_id": "BTC-USDT",
    "available": "1000.5",
    "frozen": "100.0"
}
```

### 5.3 Pydantic模型

已实现的模型（`app/api/models/schemas.py`）：

- `OKXOrderRequest` - 下单请求
- `OKXBalance` - 账户余额
- `OKXPosition` - 持仓信息
- `OKXOrderResponse` - 订单响应
- `OKXTicker` - Ticker数据


---

## 6. 测试策略

### 6.1 单元测试

**测试范围：**
- 客户端初始化（凭证验证、SDK初始化）
- 每个API方法的正常流程
- 错误处理和异常映射
- 数据格式转换

**Mock策略：**
- Mock SDK客户端（AccountAPI、TradeAPI、MarketAPI）
- Mock SDK响应数据
- 使用`pytest-asyncio`测试异步方法

**示例：**
```python
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
async def test_get_account_balance(mock_client):
    mock_client.account_api.get_account_balance = Mock(return_value={
        'code': '0',
        'data': [{'details': [...]}]
    })
    
    result = await mock_client.get_account_balance()
    assert len(result) > 0
```

### 6.2 集成测试

**测试环境：** 使用OKX模拟盘

**测试场景：**
1. 获取账户余额
2. 查询持仓
3. 下单 → 查询订单 → 撤单
4. 错误处理（无效参数、余额不足等）

### 6.3 测试覆盖率目标

- 单元测试覆盖率：≥ 90%
- 关键路径（下单、撤单）：100%

---

## 7. 实现计划

### 7.1 任务分组

**基础层（Task 1-5）：**
- Task 1: SDK验证 ✅ 已完成
- Task 2: 错误处理模块 ✅ 已完成
- Task 3: 配置管理扩展 ✅ 已完成
- Task 4: Pydantic数据模型 ✅ 已完成
- Task 5: OKXTradingClient初始化

**客户端API层（Task 6-9）：**
- Task 6: 账户余额查询API
- Task 7: 持仓查询API
- Task 8: 下单API
- Task 9: 撤单和订单查询API

**路由层（Task 10-12）：**
- Task 10: API路由 - 账户管理
- Task 11: API路由 - 交易管理
- Task 12: 集成测试和文档

### 7.2 实现顺序

1. **Task 5**：完成客户端初始化，实现`_init_sdk_clients()`
2. **Task 6-7**：实现账户管理API（余额、持仓）
3. **Task 8-9**：实现交易API（下单、撤单、查询）
4. **Task 10-12**：实现路由层（后续计划）

### 7.3 关键里程碑

- ✅ **里程碑1**：SDK验证和基础模块（Task 1-4）
- 🔄 **里程碑2**：客户端核心功能（Task 5-9）← 当前阶段
- ⏳ **里程碑3**：路由层和集成测试（Task 10-12）

---

## 8. 风险和缓解措施

### 8.1 风险识别

**风险1：凭证安全**
- **描述：** API密钥存储在`.env`文件中
- **缓解：** 
  - `.env`已加入`.gitignore`
  - 生产环境使用环境变量或密钥管理服务
  - 客户端使用私有属性存储凭证

**风险2：API频率限制**
- **描述：** OKX有严格的频率限制
- **缓解：**
  - 实现重试机制
  - 记录频率限制错误
  - 考虑实现请求队列（如需要）

**风险3：实盘/模拟盘混淆**
- **描述：** 错误使用实盘凭证可能导致真实交易
- **缓解：**
  - 明确的mode参数验证
  - 日志中标注DEMO/LIVE
  - 前端UI明确区分

### 8.2 依赖风险

**python-okx SDK：**
- 版本：0.4.1
- 维护状态：活跃
- 备选方案：如SDK停止维护，可使用httpx重新实现

---

## 9. 后续优化方向

### 9.1 性能优化

- 实现连接池复用
- 批量查询接口
- 缓存市场数据

### 9.2 功能扩展

- WebSocket实时行情推送
- 高级订单类型（止盈止损、冰山订单）
- 交易策略回测

### 9.3 监控和告警

- API调用成功率监控
- 频率限制告警
- 异常交易检测

---

## 10. 总结

本设计文档定义了OKX Trading Client的完整架构和实现方案。采用同步SDK + 异步包装器的方案，在保持实现简单性的同时，确保了FastAPI的异步性能。

**核心优势：**
- ✅ 利用现有SDK，避免重复造轮子
- ✅ 异步包装，不阻塞事件循环
- ✅ 完善的错误处理和重试机制
- ✅ 实盘/模拟盘双模式支持
- ✅ 标准化的数据格式

**下一步：** 执行Task 5-9，实现OKXTradingClient核心功能。

