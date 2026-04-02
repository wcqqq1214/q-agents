"""Connection management for MCP servers with config-driven startup and retry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.mcp_client.config import (
    DEFAULT_MCP_CONFIG_PATH,
    MCPServerConfig,
    load_mcp_server_configs,
)

logger = logging.getLogger(__name__)


class MCPToolExecutionError(RuntimeError):
    """Raised when an MCP tool returns `isError: true`."""


@dataclass
class _ManagedServerHandle:
    config: MCPServerConfig
    process: subprocess.Popen[Any] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_heartbeat_at: float = 0.0
    last_error: str | None = None
    restart_count: int = 0
    cached_tools: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pid(self) -> int | None:
        if self.process is None:
            return None
        return self.process.pid

    def process_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None


class MCPConnectionManager:
    """Owns MCP server process lifecycle, probing, and tool invocation."""

    def __init__(self, config_path: str | Path | None = None):
        self._config_path = Path(
            config_path or os.getenv("MCP_CONFIG_PATH") or DEFAULT_MCP_CONFIG_PATH
        ).resolve()
        self._servers = {
            name: _ManagedServerHandle(config=config)
            for name, config in load_mcp_server_configs(self._config_path).items()
        }

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def server_names(self) -> list[str]:
        return list(self._servers.keys())

    def _get_handle(self, server_name: str) -> _ManagedServerHandle:
        try:
            return self._servers[server_name]
        except KeyError as exc:
            raise KeyError(f"Unknown MCP server '{server_name}'") from exc

    async def ensure_all_started(self) -> None:
        """Ensure every configured managed server is reachable."""

        for server_name in self.server_names:
            await self.ensure_server(server_name)
        await self.list_registered_tools(force_refresh=True)

    async def ensure_server(self, server_name: str, *, force_probe: bool = False) -> None:
        """Ensure a single server is healthy, restarting managed ones if needed."""

        handle = self._get_handle(server_name)
        if not force_probe and self._can_skip_probe(handle):
            return

        if await self._probe_server(handle):
            return

        if not handle.config.managed:
            raise RuntimeError(
                f"MCP server '{server_name}' is unavailable at {handle.config.url}"
            )

        await self.restart_server(server_name, reason="health probe failed")

    async def restart_server(self, server_name: str, *, reason: str | None = None) -> None:
        """Restart a managed server and wait for it to become healthy."""

        handle = self._get_handle(server_name)
        if not handle.config.managed:
            raise RuntimeError(f"MCP server '{server_name}' is not a managed subprocess")

        with handle.lock:
            self._stop_process_locked(handle)
            self._start_process_locked(handle, reason=reason)

        if handle.config.restart_backoff_seconds > 0:
            await asyncio.sleep(handle.config.restart_backoff_seconds)

        await self._wait_until_healthy(handle)

    async def call_tool_json(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call an MCP tool and return decoded JSON content."""

        handle = self._get_handle(server_name)
        arguments = arguments or {}
        last_error: Exception | None = None

        for attempt in range(2):
            await self.ensure_server(server_name, force_probe=attempt > 0)

            try:
                payload = await self._call_tool_once_json(handle.config, tool_name, arguments)
                handle.last_error = None
                return payload
            except MCPToolExecutionError:
                raise
            except Exception as exc:
                last_error = exc
                handle.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "MCP tool call failed for %s/%s on attempt %d: %s",
                    server_name,
                    tool_name,
                    attempt + 1,
                    exc,
                )
                if not handle.config.managed or attempt == 1:
                    break
                await self.restart_server(
                    server_name,
                    reason=f"tool call failure for {tool_name}: {type(exc).__name__}",
                )

        raise RuntimeError(
            f"MCP server '{server_name}' could not complete tool '{tool_name}': {last_error}"
        ) from last_error

    async def list_server_tools(
        self, server_name: str, *, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """List tools exposed by one server and cache them."""

        handle = self._get_handle(server_name)
        if handle.cached_tools and not force_refresh:
            return list(handle.cached_tools)

        await self.ensure_server(server_name, force_probe=force_refresh)
        tools = await self._list_tools_once(handle.config)
        handle.cached_tools = tools
        return list(tools)

    async def list_registered_tools(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Aggregate tools across every configured server."""

        aggregated: list[dict[str, Any]] = []
        for server_name in self.server_names:
            tools = await self.list_server_tools(server_name, force_refresh=force_refresh)
            aggregated.extend([{**tool, "server_name": server_name} for tool in tools])
        return aggregated

    async def get_server_statuses(
        self, *, refresh: bool = True
    ) -> dict[str, dict[str, Any]]:
        """Return a status snapshot for every configured server."""

        statuses: dict[str, dict[str, Any]] = {}
        for server_name in self.server_names:
            handle = self._get_handle(server_name)
            available = False
            try:
                if refresh:
                    await self.ensure_server(server_name, force_probe=True)
                available = await self._probe_server(handle)
                if available and refresh:
                    await self.list_server_tools(server_name, force_refresh=True)
            except Exception as exc:
                handle.last_error = f"{type(exc).__name__}: {exc}"

            statuses[server_name] = {
                "available": available,
                "url": handle.config.base_url,
                "error": None if available else handle.last_error,
                "managed": handle.config.managed,
                "pid": handle.pid if handle.process_alive() else None,
                "tool_count": len(handle.cached_tools),
                "restart_count": handle.restart_count,
            }

        return statuses

    async def shutdown_managed_servers(self) -> None:
        """Terminate managed subprocesses started by the manager."""

        for handle in self._servers.values():
            with handle.lock:
                self._stop_process_locked(handle)

    def _can_skip_probe(self, handle: _ManagedServerHandle) -> bool:
        if handle.config.managed and handle.process is not None and not handle.process_alive():
            return False

        if handle.last_heartbeat_at <= 0:
            return False

        return (time.monotonic() - handle.last_heartbeat_at) < handle.config.heartbeat_interval_seconds

    def _stop_process_locked(self, handle: _ManagedServerHandle) -> None:
        process = handle.process
        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        handle.process = None
        handle.last_heartbeat_at = 0.0

    def _start_process_locked(
        self, handle: _ManagedServerHandle, *, reason: str | None = None
    ) -> None:
        config = handle.config
        if not config.command:
            raise RuntimeError(f"MCP server '{config.name}' does not define a launch command")

        env = os.environ.copy()
        env.update(config.env)

        logger.info(
            "Starting MCP server %s via %s %s%s",
            config.name,
            config.command,
            " ".join(config.args),
            f" ({reason})" if reason else "",
        )
        handle.process = subprocess.Popen(
            [config.command, *config.args],
            cwd=config.cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        handle.restart_count += 1
        handle.last_heartbeat_at = 0.0

    async def _wait_until_healthy(self, handle: _ManagedServerHandle) -> None:
        deadline = time.monotonic() + handle.config.startup_timeout_seconds
        last_error = handle.last_error

        while time.monotonic() < deadline:
            if handle.process is not None and handle.process.poll() is not None:
                raise RuntimeError(
                    f"MCP server '{handle.config.name}' exited early with code "
                    f"{handle.process.returncode}"
                )

            if await self._probe_server(handle):
                return

            await asyncio.sleep(0.5)
            last_error = handle.last_error

        raise RuntimeError(
            f"MCP server '{handle.config.name}' did not become healthy in "
            f"{handle.config.startup_timeout_seconds:.1f}s: {last_error}"
        )

    async def _probe_server(self, handle: _ManagedServerHandle) -> bool:
        timeout = min(5.0, handle.config.heartbeat_interval_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(handle.config.health_url)
                response.raise_for_status()
            handle.last_heartbeat_at = time.monotonic()
            handle.last_error = None
            return True
        except Exception as exc:
            handle.last_error = f"{type(exc).__name__}: {exc}"
            return False

    async def _call_tool_once_json(
        self,
        config: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        async with httpx.AsyncClient(timeout=config.startup_timeout_seconds) as http_client:
            async with streamable_http_client(config.url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    if result.isError:
                        raise MCPToolExecutionError(self._extract_tool_error_text(result.content))
                    return self._decode_result_content(result.content)

    async def _list_tools_once(self, config: MCPServerConfig) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=config.startup_timeout_seconds) as http_client:
            async with streamable_http_client(config.url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()

        tools = getattr(result, "tools", [])
        serialized: list[dict[str, Any]] = []
        for tool in tools:
            if hasattr(tool, "model_dump"):
                serialized.append(tool.model_dump(mode="json"))
            else:
                serialized.append(
                    {
                        "name": getattr(tool, "name", None),
                        "description": getattr(tool, "description", None),
                        "inputSchema": getattr(tool, "inputSchema", None),
                    }
                )
        return serialized

    @staticmethod
    def _decode_result_content(content: list[Any] | None) -> Any:
        if not content:
            return None

        decoded_parts: list[Any] = []
        for part in content:
            if not isinstance(part, TextContent) or not part.text:
                continue
            try:
                decoded_parts.append(json.loads(part.text))
            except json.JSONDecodeError:
                decoded_parts.append(part.text)

        if not decoded_parts:
            return None
        if len(decoded_parts) == 1:
            return decoded_parts[0]
        return decoded_parts

    @staticmethod
    def _extract_tool_error_text(content: list[Any] | None) -> str:
        if not content:
            return "Unknown MCP tool error"
        for part in content:
            if isinstance(part, TextContent) and part.text:
                return part.text
        return "Unknown MCP tool error"


_GLOBAL_MCP_CONNECTION_MANAGER: MCPConnectionManager | None = None


def get_mcp_connection_manager(
    config_path: str | Path | None = None,
) -> MCPConnectionManager:
    """Return a singleton manager for the default config path."""

    global _GLOBAL_MCP_CONNECTION_MANAGER
    if config_path is not None:
        return MCPConnectionManager(config_path=config_path)

    if _GLOBAL_MCP_CONNECTION_MANAGER is None:
        _GLOBAL_MCP_CONNECTION_MANAGER = MCPConnectionManager()
    return _GLOBAL_MCP_CONNECTION_MANAGER


def reset_mcp_connection_manager() -> None:
    """Clear the process manager singleton for tests."""

    global _GLOBAL_MCP_CONNECTION_MANAGER
    _GLOBAL_MCP_CONNECTION_MANAGER = None
