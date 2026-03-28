import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.graph_multi import run_once

from ..models import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


async def run_analysis_stream(query: str) -> AsyncGenerator[str, None]:
    """
    Run analysis and stream progress events.

    Calls app.graph_multi.run_once() in a background thread and streams
    progress updates as SSE events.
    """
    try:
        # Actually call the agent system
        result = await asyncio.to_thread(run_once, query)

        # Extract report ID from result
        report_id = result.get(
            "run_id", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{query.upper()}"
        )

        # Build response with full report content
        response_data = {
            "report_id": report_id,
            "status": "completed",
            "final_decision": result.get("final_decision", ""),
            "quant_analysis": result.get("quant_report_obj", {}),
            "news_sentiment": result.get("news_report_obj", {}),
            "social_sentiment": result.get("social_report_obj", {}),
        }

        # Send completion event
        yield f"data: {json.dumps({'type': 'result', 'data': response_data})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Start an analysis job (non-streaming endpoint).

    For streaming progress, use /analyze/stream endpoint.
    """
    # TODO: Implement actual analysis
    # For now, return a placeholder response
    report_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{request.query.upper()}"

    return AnalyzeResponse(report_id=report_id, status="pending")


@router.get("/analyze/stream")
async def analyze_stream(query: str):
    """
    Stream analysis progress via Server-Sent Events (SSE).

    Events:
    - type: 'progress' - Progress updates
    - type: 'result' - Final result
    - type: 'error' - Error occurred
    """
    return StreamingResponse(
        run_analysis_stream(query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
