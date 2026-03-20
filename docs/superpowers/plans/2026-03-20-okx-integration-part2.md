# OKX交易API集成实现计划 - Part 2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成OKX集成的配置管理、数据模型和客户端初始化（Task 3-5）

**Architecture:** 扩展ConfigManager支持OKX配置，添加Pydantic模型，实现OKXTradingClient基础结构

**Tech Stack:** FastAPI, Pydantic, pytest

**Prerequisites:** Task 1-2已完成（SDK验证、错误处理模块）

---

## Task 3: 配置管理扩展

**Files:**
- Modify: `app/config_manager.py`
- Test: `tests/test_config_manager_okx.py`

- [ ] **Step 1: 编写ConfigManager扩展测试**

Create `tests/test_config_manager_okx.py`:

```python
"""测试ConfigManager的OKX配置功能"""
import pytest
import os
from app.config_manager import ConfigManager


@pytest.fixture
def config_manager(tmp_path, monkeypatch):
    """创建临时ConfigManager"""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_path=env_file)

    # 设置测试环境变量
    monkeypatch.setenv("OKX_DEMO_API_KEY", "test_demo_key")
    monkeypatch.setenv("OKX_DEMO_SECRET_KEY", "test_demo_secret")
    monkeypatch.setenv("OKX_DEMO_PASSPHRASE", "test_demo_pass")

    return manager


def test_get_okx_settings_demo(config_manager):
    """测试获取demo模式配置"""
    settings = config_manager.get_okx_settings("demo")

    assert settings["mode"] == "demo"
    assert settings["api_key"] == "test_demo_key"
    assert settings["secret_key"] == "test_demo_secret"
    assert settings["passphrase"] == "test_demo_pass"


def test_get_okx_settings_live(config_manager, monkeypatch):
    """测试获取live模式配置"""
    monkeypatch.setenv("OKX_LIVE_API_KEY", "test_live_key")
    monkeypatch.setenv("OKX_LIVE_SECRET_KEY", "test_live_secret")
    monkeypatch.setenv("OKX_LIVE_PASSPHRASE", "test_live_pass")

    settings = config_manager.get_okx_settings("live")

    assert settings["mode"] == "live"
    assert settings["api_key"] == "test_live_key"


def test_update_okx_settings(config_manager):
    """测试更新OKX配置"""
    updated = config_manager.update_okx_settings(
        mode="demo",
        api_key="new_key",
        secret_key="new_secret",
        passphrase="new_pass"
    )

    assert updated["api_key"] == "new_key"
    assert updated["secret_key"] == "new_secret"
    assert updated["passphrase"] == "new_pass"

    # 验证环境变量已更新
    assert os.getenv("OKX_DEMO_API_KEY") == "new_key"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_config_manager_okx.py -v
```

Expected: 测试失败，提示方法不存在

- [ ] **Step 3: 扩展ConfigManager添加OKX方法**

在 `app/config_manager.py` 末尾添加：

```python
    def get_okx_settings(self, mode: str = "demo") -> Dict[str, Optional[str]]:
        """获取OKX配置

        Args:
            mode: 模式 (live/demo)

        Returns:
            OKX配置字典
        """
        prefix = f"OKX_{mode.upper()}_"
        return {
            "api_key": os.getenv(f"{prefix}API_KEY"),
            "secret_key": os.getenv(f"{prefix}SECRET_KEY"),
            "passphrase": os.getenv(f"{prefix}PASSPHRASE"),
            "mode": mode,
        }

    def update_okx_settings(
        self,
        mode: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """更新OKX配置

        Args:
            mode: 模式 (live/demo)
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码

        Returns:
            更新后的配置
        """
        prefix = f"OKX_{mode.upper()}_"
        updates = {}
        if api_key:
            updates[f"{prefix}API_KEY"] = api_key
        if secret_key:
            updates[f"{prefix}SECRET_KEY"] = secret_key
        if passphrase:
            updates[f"{prefix}PASSPHRASE"] = passphrase

        if updates:
            self._update_env_file(updates)

            # 更新运行时环境
            for key, value in updates.items():
                os.environ[key] = value

        return self.get_okx_settings(mode)
```

- [ ] **Step 4: 运行测试验证实现**

```bash
uv run pytest tests/test_config_manager_okx.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交配置管理扩展**

```bash
git add app/config_manager.py tests/test_config_manager_okx.py
git commit -m "feat(config): add OKX configuration management"
```

---

## Task 4: Pydantic数据模型

**Files:**
- Modify: `app/api/models/schemas.py`
- Test: `tests/test_okx_schemas.py`

- [ ] **Step 1: 编写数据模型测试**

Create `tests/test_okx_schemas.py`:

```python
"""测试OKX Pydantic模型"""
from pydantic import ValidationError
from app.api.models.schemas import (
    OKXOrderRequest,
    OKXBalance,
    OKXPosition,
    OKXOrderResponse,
    OKXTicker,
)


def test_okx_order_request_valid():
    """测试有效的下单请求"""
    order = OKXOrderRequest(
        inst_id="BTC-USDT",
        side="buy",
        order_type="limit",
        size="0.01",
        price="50000"
    )
    assert order.inst_id == "BTC-USDT"
    assert order.side == "buy"
    assert order.price == "50000"


def test_okx_order_request_market_order():
    """测试市价单（无需price）"""
    order = OKXOrderRequest(
        inst_id="BTC-USDT",
        side="sell",
        order_type="market",
        size="0.01"
    )
    assert order.price is None


def test_okx_balance():
    """测试余额模型"""
    balance = OKXBalance(
        currency="USDT",
        available="1000.5",
        frozen="100.0",
        total="1100.5"
    )
    assert balance.currency == "USDT"
    assert balance.total == "1100.5"


def test_okx_position():
    """测试持仓模型"""
    position = OKXPosition(
        inst_id="BTC-USDT-SWAP",
        position_side="long",
        position="10",
        available_position="10",
        average_price="50000",
        unrealized_pnl="500",
        leverage="10"
    )
    assert position.inst_id == "BTC-USDT-SWAP"
    assert position.position_side == "long"


def test_okx_order_response():
    """测试订单响应模型"""
    response = OKXOrderResponse(
        order_id="123456",
        client_order_id="my-order-1",
        inst_id="BTC-USDT",
        status="live",
        side="buy",
        order_type="limit",
        size="0.01",
        filled_size="0",
        price="50000",
        average_price=None,
        timestamp="2026-03-20T10:00:00Z"
    )
    assert response.order_id == "123456"
    assert response.status == "live"


def test_okx_ticker():
    """测试ticker模型"""
    ticker = OKXTicker(
        inst_id="BTC-USDT",
        last="50000",
        bid="49990",
        ask="50010",
        volume_24h="1234.56",
        high_24h="51000",
        low_24h="49000",
        timestamp="2026-03-20T10:00:00Z"
    )
    assert ticker.inst_id == "BTC-USDT"
    assert ticker.last == "50000"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_okx_schemas.py -v
```

Expected: 测试失败，提示模型不存在

- [ ] **Step 3: 在schemas.py中添加OKX模型**

在 `app/api/models/schemas.py` 末尾添加：

```python
# OKX相关模型

class OKXOrderRequest(BaseModel):
    """OKX下单请求"""
    inst_id: str
    side: str  # buy/sell
    order_type: str  # market/limit/post_only/fok/ioc
    size: str
    price: Optional[str] = None
    client_order_id: Optional[str] = None
    reduce_only: Optional[bool] = False


class OKXBalance(BaseModel):
    """OKX账户余额"""
    currency: str
    available: str
    frozen: str
    total: str


class OKXPosition(BaseModel):
    """OKX持仓信息"""
    inst_id: str
    position_side: str  # long/short/net
    position: str
    available_position: str
    average_price: str
    unrealized_pnl: str
    leverage: str


class OKXOrderResponse(BaseModel):
    """OKX订单响应"""
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
    """OKX Ticker数据"""
    inst_id: str
    last: str
    bid: str
    ask: str
    volume_24h: str
    high_24h: str
    low_24h: str
    timestamp: str
```

- [ ] **Step 4: 运行测试验证模型**

```bash
uv run pytest tests/test_okx_schemas.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交数据模型**

```bash
git add app/api/models/schemas.py tests/test_okx_schemas.py
git commit -m "feat(models): add OKX Pydantic schemas"
```

---

## Task 5: OKXTradingClient核心类（第1部分：初始化）

**Files:**
- Create: `app/okx/trading_client.py`
- Modify: `app/okx/__init__.py`
- Test: `tests/test_okx_client_init.py`

- [ ] **Step 1: 编写客户端初始化测试**

Create `tests/test_okx_client_init.py`:

```python
"""测试OKXTradingClient初始化"""
from unittest.mock import patch
from app.okx.trading_client import OKXTradingClient


def test_client_init_demo():
    """测试模拟盘客户端初始化"""
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True
        )

        assert client.api_key == "test_key"
        assert client.secret_key == "test_secret"
        assert client.passphrase == "test_pass"
        assert client.is_demo is True


def test_client_init_live():
    """测试实盘客户端初始化"""
    with patch('app.okx.trading_client.OKXTradingClient._init_sdk_clients'):
        client = OKXTradingClient(
            api_key="live_key",
            secret_key="live_secret",
            passphrase="live_pass",
            is_demo=False
        )

        assert client.is_demo is False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_okx_client_init.py -v
```

Expected: 测试失败，提示类不存在

- [ ] **Step 3: 创建OKXTradingClient基础结构**

Create `app/okx/trading_client.py`:

```python
"""OKX交易客户端"""
import logging
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .exceptions import OKXRateLimitError

logger = logging.getLogger(__name__)


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

        # 初始化SDK客户端
        self._init_sdk_clients()

        logger.info(f"[OKX-{'DEMO' if is_demo else 'LIVE'}] Client initialized")

    def _init_sdk_clients(self):
        """初始化OKX SDK客户端

        注意：此方法需要根据实际SDK API调整
        参考sdk_poc.py中验证的初始化方式
        """
        # TODO: 根据SDK POC结果实现
        # 示例：
        # import okx
        # self.account_api = okx.Account(...)
        # self.trade_api = okx.Trade(...)
        # self.market_api = okx.MarketData(...)
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry_if=retry_if_exception_type(OKXRateLimitError),
        reraise=True
    )
    async def _call_with_retry(self, func, *args, **kwargs):
        """带重试的API调用

        Args:
            func: 要调用的函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值
        """
        try:
            return await func(*args, **kwargs)
        except OKXRateLimitError as e:
            logger.warning(
                f"[OKX-{'DEMO' if self.is_demo else 'LIVE'}] "
                f"Rate limit hit, retrying... {e}"
            )
            raise
```

- [ ] **Step 4: 更新模块初始化文件**

Update `app/okx/__init__.py`:

```python
"""OKX模块"""
from typing import Dict, Optional
from .trading_client import OKXTradingClient
from .exceptions import OKXConfigError
from app.config_manager import config_manager

_client_cache: Dict[str, OKXTradingClient] = {}


def get_okx_client(mode: str = "demo", force_refresh: bool = False) -> OKXTradingClient:
    """获取OKX客户端实例（单例模式）

    Args:
        mode: 模式 (live/demo)
        force_refresh: 强制刷新客户端

    Returns:
        OKXTradingClient实例

    Raises:
        OKXConfigError: 配置缺失或无效
    """
    if mode not in ["live", "demo"]:
        raise OKXConfigError(f"Invalid mode: {mode}")

    # 强制刷新时清除缓存
    if force_refresh and mode in _client_cache:
        del _client_cache[mode]

    # 检查缓存
    if mode in _client_cache:
        return _client_cache[mode]

    # 通过ConfigManager读取配置
    settings = config_manager.get_okx_settings(mode)
    api_key = settings.get("api_key")
    secret_key = settings.get("secret_key")
    passphrase = settings.get("passphrase")

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


def clear_client_cache(mode: Optional[str] = None):
    """清除客户端缓存

    Args:
        mode: 要清除的模式，None表示清除所有
    """
    global _client_cache
    if mode:
        _client_cache.pop(mode, None)
    else:
        _client_cache.clear()


__all__ = [
    "OKXTradingClient",
    "get_okx_client",
    "clear_client_cache",
]
```

- [ ] **Step 5: 运行测试验证初始化**

```bash
uv run pytest tests/test_okx_client_init.py -v
```

Expected: 所有测试通过

- [ ] **Step 6: 提交客户端基础结构**

```bash
git add app/okx/trading_client.py app/okx/__init__.py tests/test_okx_client_init.py
git commit -m "feat(okx): add OKXTradingClient base structure"
```

---

## 执行说明

这个计划包含Task 3-5，是OKX集成的基础模块部分。

**执行方式：**
```bash
# 使用subagent-driven-development执行
claude code /superpowers:subagent-driven-development docs/superpowers/plans/2026-03-20-okx-integration-part2.md
```

**前置条件：**
- Task 1-2已完成（SDK验证、错误处理模块）
- python-okx和tenacity已安装
- .env已配置OKX credentials

**完成后：**
- 配置管理支持OKX
- Pydantic模型定义完成
- OKXTradingClient基础结构就绪
- 可以继续实现账户API、交易API等功能
