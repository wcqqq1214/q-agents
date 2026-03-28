import httpx
from fastapi import APIRouter

from ..models import MCPStatus, ServiceStatus

router = APIRouter()


async def check_service(url: str) -> ServiceStatus:
    """Check if a service is available."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            return ServiceStatus(
                available=response.status_code == 200,
                url=url,
            )
    except Exception as e:
        return ServiceStatus(
            available=False,
            url=url,
            error=str(e),
        )


@router.get("/mcp/status", response_model=MCPStatus)
async def get_mcp_status():
    """Get the status of MCP servers."""
    market_data_status = await check_service("http://localhost:8000")
    news_search_status = await check_service("http://localhost:8001")

    return MCPStatus(
        market_data=market_data_status,
        news_search=news_search_status,
    )
