"""Ensure API startup initializes the finance database schema."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_api_lifespan_initializes_finance_db(monkeypatch):
    """API startup should initialize the finance DB before serving OHLC routes."""
    import app.api.main as api_main

    if api_main.scheduler.running:
        api_main.scheduler.shutdown(wait=False)

    async def _noop_async(*_args, **_kwargs):
        return None

    class _DummyManager:
        config_path = "test-mcp-config.json"

        async def ensure_all_started(self):
            return None

        async def shutdown_managed_servers(self):
            return None

    init_calls: list[str] = []

    monkeypatch.setattr(api_main, "get_mcp_connection_manager", lambda: _DummyManager())
    monkeypatch.setattr(api_main, "create_arq_pool", AsyncMock(return_value=None))
    monkeypatch.setattr(api_main, "close_arq_pool", _noop_async)
    monkeypatch.setattr(api_main, "background_cache_warmup", _noop_async)
    monkeypatch.setattr(api_main, "background_stock_catchup", _noop_async)
    monkeypatch.setattr(api_main, "update_hot_cache_loop", _noop_async)
    monkeypatch.setattr(api_main, "init_agent_history_db", lambda _path: None)
    monkeypatch.setattr(api_main, "configure_market_data_jobs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_main, "configure_daily_digest_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api_main,
        "init_finance_db",
        lambda: init_calls.append("called"),
        raising=False,
    )

    async with api_main.app.router.lifespan_context(api_main.app):
        pass

    assert init_calls == ["called"]
