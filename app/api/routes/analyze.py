from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator

from ..models import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


async def run_analysis_stream(query: str) -> AsyncGenerator[str, None]:
    """
    Run analysis and stream progress events.

    This is a placeholder implementation. In production, this should:
    1. Call app.graph_multi.run_once() in a background thread
    2. Stream progress updates as SSE events
    3. Return the final report ID
    """
    try:
        # Send initial status
        yield f"data: {json.dumps({'type': 'progress', 'message': 'Starting analysis...'})}\n\n"
        await asyncio.sleep(0.5)

        # Simulate progress updates
        steps = [
            "Initializing agents...",
            "Fetching market data...",
            "Analyzing technical indicators...",
            "Searching for news...",
            "Analyzing sentiment...",
            "Generating report...",
        ]

        for step in steps:
            yield f"data: {json.dumps({'type': 'progress', 'message': step})}\n\n"
            await asyncio.sleep(0.5)

        # TODO: Actually call the agent system here
        # from app.graph_multi import run_once
        # result = await asyncio.to_thread(run_once, query)

        # Send completion event
        report_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{query.upper()}"
        yield f"data: {json.dumps({'type': 'result', 'data': {'report_id': report_id, 'status': 'completed'}})}\n\n"

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

    return AnalyzeResponse(
        report_id=report_id,
        status="pending"
    )


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
