"""测试订单管理功能"""

from unittest.mock import Mock, patch

import pytest

from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True,
        )
        client.trade_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_cancel_order(mock_client):
    """测试撤单"""
    mock_client.trade_api.cancel_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [{"ordId": "123456", "clOrdId": "", "sCode": "0", "sMsg": ""}],
        }
    )

    result = await mock_client.cancel_order(inst_id="BTC-USDT", order_id="123456")

    assert result["order_id"] == "123456"
    assert result["status_code"] == "0"

    # 验证SDK调用
    mock_client.trade_api.cancel_order.assert_called_once()
    call_kwargs = mock_client.trade_api.cancel_order.call_args[1]
    assert call_kwargs["instId"] == "BTC-USDT"
    assert call_kwargs["ordId"] == "123456"


@pytest.mark.asyncio
async def test_cancel_order_by_client_order_id(mock_client):
    """测试通过客户端订单ID撤单"""
    mock_client.trade_api.cancel_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [{"ordId": "123456", "clOrdId": "my-order-1", "sCode": "0", "sMsg": ""}],
        }
    )

    result = await mock_client.cancel_order(inst_id="BTC-USDT", client_order_id="my-order-1")

    assert result["order_id"] == "123456"
    call_kwargs = mock_client.trade_api.cancel_order.call_args[1]
    assert call_kwargs["clOrdId"] == "my-order-1"


@pytest.mark.asyncio
async def test_cancel_order_not_found(mock_client):
    """测试撤单失败（订单不存在）"""
    from app.okx.exceptions import OKXOrderError

    mock_client.trade_api.cancel_order = Mock(
        return_value={"code": "51400", "msg": "Order does not exist"}
    )

    with pytest.raises(OKXOrderError) as exc_info:
        await mock_client.cancel_order(inst_id="BTC-USDT", order_id="999999")

    assert exc_info.value.code == "51400"


@pytest.mark.asyncio
async def test_get_order_details(mock_client):
    """测试查询订单详情"""
    mock_client.trade_api.get_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "123456",
                    "clOrdId": "my-order-1",
                    "instId": "BTC-USDT",
                    "state": "filled",
                    "side": "buy",
                    "ordType": "limit",
                    "sz": "0.01",
                    "fillSz": "0.01",
                    "px": "50000",
                    "avgPx": "50000",
                    "cTime": "1710000000000",
                }
            ],
        }
    )

    result = await mock_client.get_order_details(inst_id="BTC-USDT", order_id="123456")

    assert result["order_id"] == "123456"
    assert result["inst_id"] == "BTC-USDT"
    assert result["status"] == "filled"
    assert result["side"] == "buy"
    assert result["order_type"] == "limit"
    assert result["size"] == "0.01"
    assert result["filled_size"] == "0.01"
    assert result["price"] == "50000"
    assert result["average_price"] == "50000"


@pytest.mark.asyncio
async def test_get_order_details_by_client_order_id(mock_client):
    """测试通过客户端订单ID查询"""
    mock_client.trade_api.get_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "123456",
                    "clOrdId": "my-order-1",
                    "instId": "BTC-USDT",
                    "state": "live",
                    "side": "buy",
                    "ordType": "limit",
                    "sz": "0.01",
                    "fillSz": "0",
                    "px": "50000",
                    "avgPx": "",
                    "cTime": "1710000000000",
                }
            ],
        }
    )

    result = await mock_client.get_order_details(inst_id="BTC-USDT", client_order_id="my-order-1")

    assert result["client_order_id"] == "my-order-1"
    assert result["status"] == "live"
    assert result["filled_size"] == "0"
    assert result["average_price"] is None


@pytest.mark.asyncio
async def test_get_order_history(mock_client):
    """测试查询历史订单"""
    mock_client.trade_api.get_orders_history = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "123456",
                    "clOrdId": "",
                    "instId": "BTC-USDT",
                    "state": "filled",
                    "side": "buy",
                    "ordType": "market",
                    "sz": "0.01",
                    "fillSz": "0.01",
                    "px": "",
                    "avgPx": "50000",
                    "cTime": "1710000000000",
                },
                {
                    "ordId": "123457",
                    "clOrdId": "",
                    "instId": "ETH-USDT",
                    "state": "canceled",
                    "side": "sell",
                    "ordType": "limit",
                    "sz": "1",
                    "fillSz": "0",
                    "px": "3000",
                    "avgPx": "",
                    "cTime": "1710000100000",
                },
            ],
        }
    )

    result = await mock_client.get_order_history(inst_type="SPOT", limit=10)

    assert len(result) == 2
    assert result[0]["order_id"] == "123456"
    assert result[0]["status"] == "filled"
    assert result[1]["order_id"] == "123457"
    assert result[1]["status"] == "canceled"

    # 验证SDK调用
    call_kwargs = mock_client.trade_api.get_orders_history.call_args[1]
    assert call_kwargs["instType"] == "SPOT"
    assert call_kwargs["limit"] == "10"


@pytest.mark.asyncio
async def test_get_order_history_empty(mock_client):
    """测试空历史订单"""
    mock_client.trade_api.get_orders_history = Mock(
        return_value={"code": "0", "msg": "", "data": []}
    )

    result = await mock_client.get_order_history(inst_type="SPOT")
    assert result == []
