"""测试OKXTradingClient下单功能"""

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
async def test_place_limit_order(mock_client):
    """测试限价单"""
    mock_client.trade_api.place_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [{"ordId": "123456", "clOrdId": "my-order-1", "sCode": "0", "sMsg": ""}],
        }
    )

    result = await mock_client.place_order(
        inst_id="BTC-USDT", side="buy", order_type="limit", size="0.01", price="50000"
    )

    assert result["order_id"] == "123456"
    assert result["client_order_id"] == "my-order-1"
    assert result["status_code"] == "0"

    # 验证SDK调用参数
    mock_client.trade_api.place_order.assert_called_once()
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert call_kwargs["instId"] == "BTC-USDT"
    assert call_kwargs["side"] == "buy"
    assert call_kwargs["ordType"] == "limit"
    assert call_kwargs["sz"] == "0.01"
    assert call_kwargs["px"] == "50000"
    assert call_kwargs["tdMode"] == "cash"


@pytest.mark.asyncio
async def test_place_market_order(mock_client):
    """测试市价单"""
    mock_client.trade_api.place_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [{"ordId": "123457", "clOrdId": "", "sCode": "0", "sMsg": ""}],
        }
    )

    result = await mock_client.place_order(
        inst_id="BTC-USDT", side="sell", order_type="market", size="0.01"
    )

    assert result["order_id"] == "123457"

    # 市价单不应该传price
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert "px" not in call_kwargs


@pytest.mark.asyncio
async def test_place_order_with_client_order_id(mock_client):
    """测试带客户端订单ID的下单"""
    mock_client.trade_api.place_order = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "123458",
                    "clOrdId": "custom-id-123",
                    "sCode": "0",
                    "sMsg": "",
                }
            ],
        }
    )

    result = await mock_client.place_order(
        inst_id="ETH-USDT",
        side="buy",
        order_type="limit",
        size="1",
        price="3000",
        client_order_id="custom-id-123",
    )

    assert result["client_order_id"] == "custom-id-123"
    call_kwargs = mock_client.trade_api.place_order.call_args[1]
    assert call_kwargs["clOrdId"] == "custom-id-123"


@pytest.mark.asyncio
async def test_place_order_insufficient_balance(mock_client):
    """测试余额不足错误"""
    from app.okx.exceptions import OKXInsufficientBalanceError

    mock_client.trade_api.place_order = Mock(
        return_value={"code": "51008", "msg": "Insufficient balance"}
    )

    with pytest.raises(OKXInsufficientBalanceError) as exc_info:
        await mock_client.place_order(
            inst_id="BTC-USDT", side="buy", order_type="market", size="100"
        )

    assert exc_info.value.code == "51008"


@pytest.mark.asyncio
async def test_place_order_error(mock_client):
    """测试下单错误"""
    from app.okx.exceptions import OKXOrderError

    mock_client.trade_api.place_order = Mock(
        return_value={"code": "51000", "msg": "Order placement failed"}
    )

    with pytest.raises(OKXOrderError):
        await mock_client.place_order(
            inst_id="BTC-USDT",
            side="buy",
            order_type="limit",
            size="0.01",
            price="50000",
        )
