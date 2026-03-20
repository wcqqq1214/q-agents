"""API routes for agent decision history."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os

from app.database.agent_history import (
    query_analysis_runs,
    query_run_detail,
    query_agent_messages,
    query_tool_calls
)

router = APIRouter()


@router.get("/analysis-runs")
async def get_analysis_runs(
    asset: Optional[str] = Query(None, description="Filter by asset ticker"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """Query analysis runs with optional filters."""
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")

    results = query_analysis_runs(
        asset=asset,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        db_path=db_path
    )

    return {
        "total": len(results),
        "items": results
    }


@router.get("/analysis-runs/{run_id}")
async def get_run_detail(run_id: str):
    """Get detailed information for a single analysis run."""
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")

    result = query_run_detail(run_id, db_path=db_path)

    if not result:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return result


@router.get("/agent-executions/{execution_id}/messages")
async def get_agent_messages(execution_id: str):
    """Get complete message history for an agent execution."""
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")

    result = query_agent_messages(execution_id, db_path=db_path)

    if not result:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return result


@router.get("/tool-calls")
async def get_tool_calls(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    status: Optional[str] = Query(None, description="Filter by status (success/failed)"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """Query tool calls with optional filters."""
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")

    results = query_tool_calls(
        tool_name=tool_name,
        status=status,
        date_from=date_from,
        limit=limit,
        offset=offset,
        db_path=db_path
    )

    return {
        "total": len(results),
        "items": results
    }


@router.get("/tool-calls/stats")
async def get_tool_stats(
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)")
):
    """Get tool usage statistics."""
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")

    # Query all tool calls in the period
    all_calls = query_tool_calls(
        date_from=date_from,
        limit=10000,  # Large limit to get all
        db_path=db_path
    )

    # Aggregate by tool_name
    stats_by_tool = {}
    for call in all_calls:
        tool_name = call["tool_name"]
        if tool_name not in stats_by_tool:
            stats_by_tool[tool_name] = {
                "tool_name": tool_name,
                "total_calls": 0,
                "success_count": 0,
                "failed_count": 0
            }

        stats_by_tool[tool_name]["total_calls"] += 1
        if call["status"] == "success":
            stats_by_tool[tool_name]["success_count"] += 1
        elif call["status"] == "failed":
            stats_by_tool[tool_name]["failed_count"] += 1

    # Calculate success rate
    tools = []
    for tool_stats in stats_by_tool.values():
        total = tool_stats["total_calls"]
        success = tool_stats["success_count"]
        tool_stats["success_rate"] = success / total if total > 0 else 0.0
        tools.append(tool_stats)

    return {
        "period": {
            "from": date_from,
            "to": date_to
        },
        "tools": tools
    }
