"""测试OKXTradingClient持仓功能"""

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
        client.account_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_get_positions_all(mock_client):
    """测试获取所有持仓"""
    mock_client.account_api.get_positions = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "posSide": "long",
                    "pos": "10",
                    "availPos": "10",
                    "avgPx": "50000",
                    "upl": "500",
                    "lever": "10",
                },
                {
                    "instId": "ETH-USDT-SWAP",
                    "posSide": "short",
                    "pos": "20",
                    "availPos": "20",
                    "avgPx": "3000",
                    "upl": "-100",
                    "lever": "5",
                },
            ],
        }
    )

    result = await mock_client.get_positions()

    assert len(result) == 2
    assert result[0]["inst_id"] == "BTC-USDT-SWAP"
    assert result[0]["position_side"] == "long"
    assert result[0]["position"] == "10"
    assert result[0]["average_price"] == "50000"
    assert result[1]["inst_id"] == "ETH-USDT-SWAP"


@pytest.mark.asyncio
async def test_get_positions_by_inst_type(mock_client):
    """测试按产品类型获取持仓"""
    mock_client.account_api.get_positions = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instId": "BTC-USDT",
                    "posSide": "net",
                    "pos": "0.5",
                    "availPos": "0.5",
                    "avgPx": "50000",
                    "upl": "0",
                    "lever": "1",
                }
            ],
        }
    )

    result = await mock_client.get_positions(inst_type="SPOT")

    assert len(result) == 1
    assert result[0]["inst_id"] == "BTC-USDT"
    mock_client.account_api.get_positions.assert_called_once_with(instType="SPOT")


@pytest.mark.asyncio
async def test_get_positions_empty(mock_client):
    """测试空持仓"""
    mock_client.account_api.get_positions = Mock(return_value={"code": "0", "msg": "", "data": []})

    result = await mock_client.get_positions()
    assert result == []


@pytest.mark.asyncio
async def test_get_positions_error(mock_client):
    """测试持仓查询错误"""
    from app.okx.exceptions import OKXAuthError

    mock_client.account_api.get_positions = Mock(
        return_value={"code": "50113", "msg": "Invalid Sign"}
    )

    with pytest.raises(OKXAuthError):
        await mock_client.get_positions()
