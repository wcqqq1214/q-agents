"""Helpers for loading MCP server configuration from JSON."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MCP_CONFIG_PATH = PROJECT_ROOT / "mcp_config.json"


@dataclass(frozen=True)
class MCPServerConfig:
    """Normalized MCP server configuration."""

    name: str
    transport: str
    url: str
    health_url: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    heartbeat_interval_seconds: float = 10.0
    startup_timeout_seconds: float = 20.0
    restart_backoff_seconds: float = 1.0

    @property
    def managed(self) -> bool:
        return bool(self.command)

    @property
    def base_url(self) -> str:
        return strip_mcp_suffix(self.url)


def _expand(value: str) -> str:
    return os.path.expandvars(value)


def _resolve_cwd(raw_cwd: str | None) -> str:
    if not raw_cwd:
        return str(PROJECT_ROOT)
    expanded = Path(_expand(raw_cwd))
    if expanded.is_absolute():
        return str(expanded)
    return str((PROJECT_ROOT / expanded).resolve())


def _server_env_var(server_name: str, suffix: str) -> str:
    return f"MCP_{server_name.upper()}_{suffix}".replace("-", "_")


def ensure_mcp_endpoint(url: str) -> str:
    """Normalize a base URL or endpoint URL into a `/mcp` endpoint URL."""

    normalized = url.rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/mcp"):
        return normalized
    return f"{normalized}/mcp"


def strip_mcp_suffix(url: str) -> str:
    """Convert an MCP endpoint URL into its server base URL."""

    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")]
    if not path:
        path = "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")


def _build_server_config(name: str, raw: dict[str, Any]) -> MCPServerConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"MCP server '{name}' must be an object in mcp_config.json")

    transport = str(raw.get("transport", "streamable_http"))
    if transport != "streamable_http":
        raise ValueError(
            f"MCP server '{name}' uses unsupported transport '{transport}'. "
            "Only streamable_http is supported in q-agents."
        )

    url_override = os.getenv(_server_env_var(name, "URL"))
    url = ensure_mcp_endpoint(_expand(url_override or raw.get("url", "")))
    if not url:
        raise ValueError(f"MCP server '{name}' must define a non-empty 'url'")

    raw_health_url = os.getenv(_server_env_var(name, "HEALTH_URL")) or raw.get("health_url")
    health_url = _expand(str(raw_health_url)) if raw_health_url else f"{strip_mcp_suffix(url)}/health"

    command = raw.get("command")
    if command is not None:
        command = _expand(str(command))

    args = tuple(_expand(str(item)) for item in raw.get("args", []))
    env = {str(key): _expand(str(value)) for key, value in raw.get("env", {}).items()}

    return MCPServerConfig(
        name=name,
        transport=transport,
        url=url,
        health_url=health_url,
        command=command,
        args=args,
        env=env,
        cwd=_resolve_cwd(raw.get("cwd")),
        heartbeat_interval_seconds=float(raw.get("heartbeat_interval_seconds", 10.0)),
        startup_timeout_seconds=float(raw.get("startup_timeout_seconds", 20.0)),
        restart_backoff_seconds=float(raw.get("restart_backoff_seconds", 1.0)),
    )


@lru_cache(maxsize=8)
def _load_mcp_server_configs_cached(config_path: str) -> dict[str, MCPServerConfig]:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    servers = payload.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcp_config.json must define an object at key 'mcpServers'")

    return {name: _build_server_config(name, raw) for name, raw in servers.items()}


def load_mcp_server_configs(config_path: str | Path | None = None) -> dict[str, MCPServerConfig]:
    """Load and normalize MCP server configuration."""

    resolved_path = Path(config_path or os.getenv("MCP_CONFIG_PATH") or DEFAULT_MCP_CONFIG_PATH)
    return _load_mcp_server_configs_cached(str(resolved_path.resolve()))


def clear_mcp_server_config_cache() -> None:
    """Clear cached MCP config state for tests or explicit reloads."""

    _load_mcp_server_configs_cached.cache_clear()


def get_mcp_server_config(
    server_name: str, config_path: str | Path | None = None
) -> MCPServerConfig:
    """Return the normalized configuration for a single server."""

    configs = load_mcp_server_configs(config_path=config_path)
    try:
        return configs[server_name]
    except KeyError as exc:
        raise KeyError(f"Unknown MCP server '{server_name}'") from exc


def get_configured_mcp_server_base_urls(
    config_path: str | Path | None = None,
) -> dict[str, str]:
    """Return a mapping of server name to base URL without the `/mcp` suffix."""

    return {
        name: config.base_url
        for name, config in load_mcp_server_configs(config_path=config_path).items()
    }
