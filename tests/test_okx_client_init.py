"""测试OKXTradingClient初始化"""
import pytest
from unittest.mock import Mock, patch
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
