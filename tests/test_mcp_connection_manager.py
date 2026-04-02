import json

import pytest

from app.mcp_client.connection_manager import MCPConnectionManager


def _write_config(tmp_path):
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "market_data": {
                        "url": "http://127.0.0.1:8000/mcp",
                        "health_url": "http://127.0.0.1:8000/health",
                        "command": "uv",
                        "args": ["run", "python", "-m", "mcp_servers.market_data.main"],
                    },
                    "news_search": {
                        "url": "http://127.0.0.1:8001/mcp",
                        "health_url": "http://127.0.0.1:8001/health",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.mark.asyncio
async def test_call_tool_json_retries_after_restart(monkeypatch, tmp_path):
    manager = MCPConnectionManager(_write_config(tmp_path))
    restart_calls = []
    attempts = {"count": 0}

    async def fake_ensure_server(server_name: str, *, force_probe: bool = False) -> None:
        assert server_name == "market_data"

    async def fake_restart_server(server_name: str, *, reason: str | None = None) -> None:
        restart_calls.append((server_name, reason))

    async def fake_call_tool_once_json(config, tool_name, arguments):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("connection refused")
        return {"symbol": arguments["ticker"], "price": 123.45}

    monkeypatch.setattr(manager, "ensure_server", fake_ensure_server)
    monkeypatch.setattr(manager, "restart_server", fake_restart_server)
    monkeypatch.setattr(manager, "_call_tool_once_json", fake_call_tool_once_json)

    payload = await manager.call_tool_json(
        "market_data",
        "get_us_stock_quote",
        {"ticker": "AAPL"},
    )

    assert payload["symbol"] == "AAPL"
    assert attempts["count"] == 2
    assert restart_calls


@pytest.mark.asyncio
async def test_list_registered_tools_aggregates_server_name(monkeypatch, tmp_path):
    manager = MCPConnectionManager(_write_config(tmp_path))

    async def fake_list_server_tools(server_name: str, *, force_refresh: bool = False):
        return [{"name": f"{server_name}_tool"}]

    monkeypatch.setattr(manager, "list_server_tools", fake_list_server_tools)

    tools = await manager.list_registered_tools(force_refresh=True)

    assert tools == [
        {"name": "market_data_tool", "server_name": "market_data"},
        {"name": "news_search_tool", "server_name": "news_search"},
    ]
