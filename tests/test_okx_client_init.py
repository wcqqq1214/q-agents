"""测试OKXTradingClient初始化"""

from unittest.mock import patch

import pytest

from app.okx import clear_client_cache, get_okx_client
from app.okx.exceptions import OKXConfigError
from app.okx.trading_client import OKXTradingClient


def test_client_init_demo():
    """测试模拟盘客户端初始化"""
    with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
        client = OKXTradingClient(
            api_key="test_key",
            secret_key="test_secret",
            passphrase="test_pass",
            is_demo=True,
        )

        assert client._api_key == "test_key"
        assert client._secret_key == "test_secret"
        assert client._passphrase == "test_pass"
        assert client.is_demo is True


def test_client_init_live():
    """测试实盘客户端初始化"""
    with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
        client = OKXTradingClient(
            api_key="live_key",
            secret_key="live_secret",
            passphrase="live_pass",
            is_demo=False,
        )

        assert client.is_demo is False


def test_client_init_empty_api_key():
    """测试空API密钥应该抛出ValueError"""
    with pytest.raises(ValueError, match="api_key cannot be empty"):
        OKXTradingClient(api_key="", secret_key="test_secret", passphrase="test_pass")


def test_client_init_empty_secret_key():
    """测试空Secret密钥应该抛出ValueError"""
    with pytest.raises(ValueError, match="secret_key cannot be empty"):
        OKXTradingClient(api_key="test_key", secret_key="", passphrase="test_pass")


def test_client_init_empty_passphrase():
    """测试空密码应该抛出ValueError"""
    with pytest.raises(ValueError, match="passphrase cannot be empty"):
        OKXTradingClient(api_key="test_key", secret_key="test_secret", passphrase="")


def test_get_okx_client_demo():
    """测试获取demo模式客户端"""
    clear_client_cache()

    with patch("app.okx.config_manager.get_okx_settings") as mock_config:
        mock_config.return_value = {
            "api_key": "demo_key",
            "secret_key": "demo_secret",
            "passphrase": "demo_pass",
        }

        with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
            client = get_okx_client(mode="demo")

            assert client is not None
            assert client.is_demo is True


def test_get_okx_client_cache():
    """测试客户端缓存功能"""
    clear_client_cache()

    with patch("app.okx.config_manager.get_okx_settings") as mock_config:
        mock_config.return_value = {
            "api_key": "demo_key",
            "secret_key": "demo_secret",
            "passphrase": "demo_pass",
        }

        with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
            client1 = get_okx_client(mode="demo")
            client2 = get_okx_client(mode="demo")

            # 应该返回同一个实例
            assert client1 is client2


def test_get_okx_client_force_refresh():
    """测试强制刷新客户端"""
    clear_client_cache()

    with patch("app.okx.config_manager.get_okx_settings") as mock_config:
        mock_config.return_value = {
            "api_key": "demo_key",
            "secret_key": "demo_secret",
            "passphrase": "demo_pass",
        }

        with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
            client1 = get_okx_client(mode="demo")
            client2 = get_okx_client(mode="demo", force_refresh=True)

            # 应该返回不同的实例
            assert client1 is not client2


def test_get_okx_client_invalid_mode():
    """测试无效模式应该抛出OKXConfigError"""
    with pytest.raises(OKXConfigError, match="Invalid mode: invalid"):
        get_okx_client(mode="invalid")


def test_get_okx_client_missing_config():
    """测试缺失配置应该抛出OKXConfigError"""
    clear_client_cache()

    with patch("app.okx.config_manager.get_okx_settings") as mock_config:
        mock_config.return_value = {
            "api_key": "demo_key",
            "secret_key": "",  # 空secret_key
            "passphrase": "demo_pass",
        }

        with pytest.raises(OKXConfigError, match="Missing OKX demo configuration"):
            get_okx_client(mode="demo")


def test_clear_client_cache():
    """测试清除客户端缓存"""
    clear_client_cache()

    with patch("app.okx.config_manager.get_okx_settings") as mock_config:
        mock_config.return_value = {
            "api_key": "demo_key",
            "secret_key": "demo_secret",
            "passphrase": "demo_pass",
        }

        with patch("app.okx.trading_client.OKXTradingClient._init_sdk_clients"):
            client1 = get_okx_client(mode="demo")
            clear_client_cache(mode="demo")
            client2 = get_okx_client(mode="demo")

            # 清除缓存后应该返回不同的实例
            assert client1 is not client2
