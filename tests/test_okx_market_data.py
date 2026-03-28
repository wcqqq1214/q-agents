"""测试OKXTradingClient市场数据功能"""

from unittest.mock import Mock, patch

import pytest

from app.okx.trading_client import OKXTradingClient


@pytest.fixture
def mock_client():
    """创建mock客户端"""
    with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True,
        )
        client.market_api = Mock()
        yield client


@pytest.mark.asyncio
async def test_get_candles_success(mock_client):
    """测试成功获取K线数据"""
    mock_client.market_api.get_candlesticks = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                [
                    "1597026383085",
                    "3.721",
                    "3.743",
                    "3.677",
                    "3.708",
                    "8422410",
                    "22698348.04",
                ],
                [
                    "1597026383086",
                    "3.730",
                    "3.750",
                    "3.680",
                    "3.715",
                    "8500000",
                    "23000000.00",
                ],
            ],
        }
    )

    result = await mock_client.get_candles("BTC-USDT", bar="15m", limit=100)

    # 验证返回类型
    assert isinstance(result, list)
    assert len(result) == 2

    # 验证数据结构
    assert "ts" in result[0]
    assert "o" in result[0]
    assert "h" in result[0]
    assert "l" in result[0]
    assert "c" in result[0]
    assert "vol" in result[0]

    # 验证数据值
    assert result[0]["ts"] == "1597026383085"
    assert result[0]["o"] == "3.721"
    assert result[0]["h"] == "3.743"
    assert result[0]["l"] == "3.677"
    assert result[0]["c"] == "3.708"
    assert result[0]["vol"] == "8422410"

    # 验证API调用参数
    mock_client.market_api.get_candlesticks.assert_called_once_with(
        instId="BTC-USDT", bar="15m", limit="100", after="", before=""
    )


@pytest.mark.asyncio
async def test_get_candles_invalid_symbol(mock_client):
    """测试无效symbol处理"""
    from app.okx.exceptions import OKXError

    mock_client.market_api.get_candlesticks = Mock(
        return_value={"code": "51001", "msg": "Instrument ID does not exist"}
    )

    with pytest.raises(OKXError) as exc_info:
        await mock_client.get_candles("INVALID-SYMBOL")

    assert "Instrument ID does not exist" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_ticker_success(mock_client):
    """测试成功获取ticker数据"""
    mock_client.market_api.get_ticker = Mock(
        return_value={
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instId": "BTC-USDT",
                    "last": "50000.5",
                    "open24h": "49000.0",
                    "high24h": "51000.0",
                    "low24h": "48500.0",
                    "vol24h": "12345.67",
                }
            ],
        }
    )

    result = await mock_client.get_ticker("BTC-USDT")

    # 验证返回类型
    assert isinstance(result, dict)

    # 验证数据结构
    assert "instId" in result
    assert "last" in result
    assert "open24h" in result
    assert "high24h" in result
    assert "low24h" in result
    assert "vol24h" in result

    # 验证数据值
    assert result["instId"] == "BTC-USDT"
    assert result["last"] == "50000.5"
    assert result["open24h"] == "49000.0"
    assert result["high24h"] == "51000.0"
    assert result["low24h"] == "48500.0"
    assert result["vol24h"] == "12345.67"

    # 验证API调用参数
    mock_client.market_api.get_ticker.assert_called_once_with(instId="BTC-USDT")


@pytest.mark.asyncio
async def test_get_ticker_no_data(mock_client):
    """测试ticker无数据场景"""
    from app.okx.exceptions import OKXError

    mock_client.market_api.get_ticker = Mock(return_value={"code": "0", "msg": "", "data": []})

    with pytest.raises(OKXError) as exc_info:
        await mock_client.get_ticker("BTC-USDT")

    assert "No ticker data" in str(exc_info.value)
