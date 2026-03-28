"""测试OKX Pydantic模型"""

from app.api.models.schemas import (
    OKXBalance,
    OKXOrderRequest,
    OKXOrderResponse,
    OKXPosition,
    OKXTicker,
)


def test_okx_order_request_valid():
    """测试有效的下单请求"""
    order = OKXOrderRequest(
        inst_id="BTC-USDT", side="buy", order_type="limit", size="0.01", price="50000"
    )
    assert order.inst_id == "BTC-USDT"
    assert order.side == "buy"
    assert order.price == "50000"


def test_okx_order_request_market_order():
    """测试市价单（无需price）"""
    order = OKXOrderRequest(inst_id="BTC-USDT", side="sell", order_type="market", size="0.01")
    assert order.price is None


def test_okx_balance():
    """测试余额模型"""
    balance = OKXBalance(currency="USDT", available="1000.5", frozen="100.0", total="1100.5")
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
        leverage="10",
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
        timestamp="2026-03-20T10:00:00Z",
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
        timestamp="2026-03-20T10:00:00Z",
    )
    assert ticker.inst_id == "BTC-USDT"
    assert ticker.last == "50000"
