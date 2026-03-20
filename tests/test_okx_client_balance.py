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
