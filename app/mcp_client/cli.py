"""CLI helpers for bootstrapping configured MCP servers."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.mcp_client.connection_manager import get_mcp_connection_manager


async def _run_start_all() -> None:
    manager = get_mcp_connection_manager()
    await manager.ensure_all_started()
    statuses = await manager.get_server_statuses(refresh=False)
    print(json.dumps(statuses, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage q-agents MCP servers")
    parser.add_argument(
        "command",
        choices=["start-all"],
        help="Operation to run against configured MCP servers",
    )
    args = parser.parse_args()

    if args.command == "start-all":
        asyncio.run(_run_start_all())


if __name__ == "__main__":
    main()
