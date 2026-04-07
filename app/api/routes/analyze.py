import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.analysis import AnalysisRuntime
from app.graph_multi import run_once

from ..models import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


HEARTBEAT_INTERVAL_SECONDS = 1.0


def _format_sse(payload: dict[str, Any]) -> str:
    """Serialize a normalized event payload into SSE format."""

    return f"data: {json.dumps(payload)}\n\n"


def _build_response_data(result: dict[str, Any], query: str) -> dict[str, Any]:
    """Build the final frontend payload from a completed analysis result."""

    report_id = result.get("run_id", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{query.upper()}")
    return {
        "report_id": report_id,
        "status": "completed",
        "final_decision": result.get("final_decision", ""),
        "quant_analysis": result.get("quant_report_obj", {}),
        "news_sentiment": result.get("news_report_obj", {}),
        "social_sentiment": result.get("social_report_obj", {}),
        "reports": {
            "cio": result.get("final_decision", ""),
            "quant": (
                result.get("quant_report_obj", {}).get("markdown_report")
                if isinstance(result.get("quant_report_obj"), dict)
                else None
            ),
            "news": (
                result.get("news_report_obj", {}).get("markdown_report")
                if isinstance(result.get("news_report_obj"), dict)
                else None
            ),
            "social": (
                result.get("social_report_obj", {}).get("markdown_report")
                if isinstance(result.get("social_report_obj"), dict)
                else None
            ),
        },
    }


async def run_analysis_stream(query: str) -> AsyncGenerator[str, None]:
    """
    Run analysis and stream progress events.

    Calls app.graph_multi.run_once() in a background thread and streams
    progress updates as SSE events.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime = AnalysisRuntime(
        run_id=f"stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        loop=loop,
        public_queue=queue,
        db_path=None,
    )
    analysis_task = asyncio.create_task(asyncio.to_thread(run_once, query, runtime=runtime))

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
                yield _format_sse(event)
                if event.get("type") in {"result", "error"}:
                    break
                continue
            except asyncio.TimeoutError:
                if not analysis_task.done():
                    heartbeat = {
                        "type": "heartbeat",
                        "stage": "system",
                        "status": "running",
                        "message": "Analysis still running",
                    }
                    yield _format_sse(heartbeat)
                    continue

            if analysis_task.done():
                try:
                    result = analysis_task.result()
                except Exception as exc:  # noqa: BLE001
                    runtime.emit_error("system", str(exc))
                else:
                    response_data = _build_response_data(result, query)
                    runtime.bind_run_id(response_data["report_id"])
                    runtime.emit_result(response_data)
                continue
    finally:
        runtime.close_public_stream()
        if not analysis_task.done():
            analysis_task.cancel()


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
