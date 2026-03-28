"""测试ConfigManager的OKX配置功能"""

import os

import pytest

from app.config_manager import ConfigManager


@pytest.fixture
def config_manager(tmp_path, monkeypatch):
    """创建临时ConfigManager"""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_path=env_file)

    # 设置测试环境变量
    monkeypatch.setenv("OKX_DEMO_API_KEY", "test_demo_key")
    monkeypatch.setenv("OKX_DEMO_SECRET_KEY", "test_demo_secret")
    monkeypatch.setenv("OKX_DEMO_PASSPHRASE", "test_demo_pass")

    return manager


def test_get_okx_settings_demo(config_manager):
    """测试获取demo模式配置"""
    settings = config_manager.get_okx_settings("demo")

    assert settings["mode"] == "demo"
    assert settings["api_key"] == "test_demo_key"
    assert settings["secret_key"] == "test_demo_secret"
    assert settings["passphrase"] == "test_demo_pass"


def test_get_okx_settings_live(config_manager, monkeypatch):
    """测试获取live模式配置"""
    monkeypatch.setenv("OKX_LIVE_API_KEY", "test_live_key")
    monkeypatch.setenv("OKX_LIVE_SECRET_KEY", "test_live_secret")
    monkeypatch.setenv("OKX_LIVE_PASSPHRASE", "test_live_pass")

    settings = config_manager.get_okx_settings("live")

    assert settings["mode"] == "live"
    assert settings["api_key"] == "test_live_key"
    assert settings["secret_key"] == "test_live_secret"
    assert settings["passphrase"] == "test_live_pass"


def test_update_okx_settings(config_manager):
    """测试更新OKX配置"""
    updated = config_manager.update_okx_settings(
        mode="demo", api_key="new_key", secret_key="new_secret", passphrase="new_pass"
    )

    assert updated["api_key"] == "new_key"
    assert updated["secret_key"] == "new_secret"
    assert updated["passphrase"] == "new_pass"

    # 验证环境变量已更新
    assert os.getenv("OKX_DEMO_API_KEY") == "new_key"


def test_invalid_mode_get_raises_error(config_manager):
    """测试get_okx_settings使用无效mode抛出错误"""
    with pytest.raises(ValueError, match="Invalid mode: invalid. Must be 'live' or 'demo'"):
        config_manager.get_okx_settings("invalid")


def test_invalid_mode_update_raises_error(config_manager):
    """测试update_okx_settings使用无效mode抛出错误"""
    with pytest.raises(ValueError, match="Invalid mode: production. Must be 'live' or 'demo'"):
        config_manager.update_okx_settings(mode="production", api_key="test_key")


def test_partial_update(config_manager):
    """测试部分更新OKX配置"""
    # 只更新api_key
    updated = config_manager.update_okx_settings(mode="demo", api_key="only_new_key")

    assert updated["api_key"] == "only_new_key"
    # 其他字段保持原值
    assert updated["secret_key"] == "test_demo_secret"
    assert updated["passphrase"] == "test_demo_pass"


def test_empty_strings_ignored(config_manager):
    """测试空字符串不会更新配置"""
    # 尝试用空字符串更新
    updated = config_manager.update_okx_settings(
        mode="demo", api_key="", secret_key="", passphrase=""
    )

    # 应该保持原值
    assert updated["api_key"] == "test_demo_key"
    assert updated["secret_key"] == "test_demo_secret"
    assert updated["passphrase"] == "test_demo_pass"


def test_get_redis_settings(config_manager, monkeypatch):
    """测试获取 Redis 配置"""
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("REDIS_ENABLED", "false")
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "42")

    settings = config_manager.get_redis_settings()

    assert settings["redis_url"] == "redis://redis:6379/1"
    assert settings["redis_enabled"] is False
    assert settings["max_connections"] == 42


def test_update_redis_settings(config_manager):
    """测试更新 Redis 配置"""
    updated = config_manager.update_redis_settings(
        redis_url="redis://localhost:6380/2",
        redis_enabled=False,
    )

    assert updated["redis_url"] == "redis://localhost:6380/2"
    assert updated["redis_enabled"] is False
    assert os.getenv("REDIS_URL") == "redis://localhost:6380/2"
    assert os.getenv("REDIS_ENABLED") == "false"
