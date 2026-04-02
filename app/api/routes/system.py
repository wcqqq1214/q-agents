from fastapi import APIRouter

from app.mcp_client.connection_manager import get_mcp_connection_manager

from ..models import MCPStatus, ServiceStatus

router = APIRouter()


@router.get("/mcp/status", response_model=MCPStatus)
async def get_mcp_status():
    """Get the status of configured MCP servers."""

    statuses = await get_mcp_connection_manager().get_server_statuses(refresh=True)
    service_statuses = {
        name: ServiceStatus(**payload) for name, payload in statuses.items()
    }

    return MCPStatus(
        market_data=service_statuses.get("market_data"),
        news_search=service_statuses.get("news_search"),
        servers=service_statuses,
    )
