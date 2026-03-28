"""OKX集成端到端测试（使用模拟盘）"""

import asyncio

import pytest

from app.okx import clear_client_cache, get_okx_client


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
        assert "currency" in balance
        assert "available" in balance
        assert "frozen" in balance
        assert "total" in balance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_positions_integration(okx_client):
    """集成测试：获取持仓"""
    positions = await okx_client.get_positions(inst_type="SPOT")

    # 验证返回格式
    assert isinstance(positions, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_lifecycle_integration(okx_client):
    """集成测试：订单生命周期（下单 → 查询 → 撤单）"""

    # 1. 下单（限价单，价格设置得很低，不会成交）
    order_result = await okx_client.place_order(
        inst_id="BTC-USDT",
        side="buy",
        order_type="limit",
        size="0.001",
        price="10000",
        client_order_id=f"test-{int(asyncio.get_event_loop().time())}",
    )

    assert "order_id" in order_result
    order_id = order_result["order_id"]

    await asyncio.sleep(1)

    # 2. 查询订单详情
    order_details = await okx_client.get_order_details(inst_id="BTC-USDT", order_id=order_id)

    assert order_details["order_id"] == order_id
    assert order_details["status"] in ["live", "partially_filled"]

    # 3. 撤单
    cancel_result = await okx_client.cancel_order(inst_id="BTC-USDT", order_id=order_id)

    assert cancel_result["order_id"] == order_id

    await asyncio.sleep(1)

    # 4. 验证已撤单
    order_details_after = await okx_client.get_order_details(inst_id="BTC-USDT", order_id=order_id)

    assert order_details_after["status"] == "canceled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_order_history_integration(okx_client):
    """集成测试：查询历史订单"""
    orders = await okx_client.get_order_history(inst_type="SPOT", limit=10)

    assert isinstance(orders, list)


@pytest.mark.integration
def test_client_singleton():
    """集成测试：客户端单例模式"""
    client1 = get_okx_client(mode="demo")
    client2 = get_okx_client(mode="demo")

    assert client1 is client2

    client3 = get_okx_client(mode="demo", force_refresh=True)
    assert client3 is not client1

    clear_client_cache()
