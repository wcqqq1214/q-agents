import json

from app.mcp_client.config import (
    clear_mcp_server_config_cache,
    get_configured_mcp_server_base_urls,
    load_mcp_server_configs,
)


def test_load_mcp_server_configs_normalizes_urls(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "market_data": {
                        "url": "http://127.0.0.1:8010",
                        "health_url": "http://127.0.0.1:8010/health",
                        "command": "uv",
                        "args": ["run", "python", "-m", "mcp_servers.market_data.main"],
                        "cwd": ".",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MCP_MARKET_DATA_URL", "http://localhost:9900/custom")
    clear_mcp_server_config_cache()

    configs = load_mcp_server_configs(config_path)
    server = configs["market_data"]

    assert server.url == "http://localhost:9900/custom/mcp"
    assert server.base_url == "http://localhost:9900/custom"
    assert server.managed is True
    assert server.command == "uv"


def test_get_configured_mcp_server_base_urls(tmp_path):
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "market_data": {"url": "http://127.0.0.1:8000/mcp"},
                    "news_search": {"url": "http://127.0.0.1:8001/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )

    clear_mcp_server_config_cache()
    urls = get_configured_mcp_server_base_urls(config_path)

    assert urls == {
        "market_data": "http://127.0.0.1:8000",
        "news_search": "http://127.0.0.1:8001",
    }
