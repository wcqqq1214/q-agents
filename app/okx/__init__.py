"""OKX模块"""

import threading
from typing import Dict, Optional

from app.config_manager import config_manager

from .exceptions import OKXConfigError
from .trading_client import OKXTradingClient

_client_cache: Dict[str, OKXTradingClient] = {}
_cache_lock = threading.Lock()


def get_okx_client(mode: str = "demo", force_refresh: bool = False) -> OKXTradingClient:
    """获取OKX客户端实例（单例模式，线程安全）

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

    with _cache_lock:
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
            is_demo=(mode == "demo"),
        )

        # 缓存
        _client_cache[mode] = client
        return client


def clear_client_cache(mode: Optional[str] = None):
    """清除客户端缓存（线程安全）

    Args:
        mode: 要清除的模式，None表示清除所有
    """
    with _cache_lock:
        if mode:
            _client_cache.pop(mode, None)
        else:
            _client_cache.clear()


__all__ = [
    "OKXTradingClient",
    "get_okx_client",
    "clear_client_cache",
]
