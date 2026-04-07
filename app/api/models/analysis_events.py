"""Typed models for public analysis streaming events."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnalysisEventType = Literal["stage", "tool_call", "tool_result", "result", "error", "heartbeat"]
AnalysisStage = Literal["system", "quant", "news", "social", "cio"]
AnalysisEventStatus = Literal["pending", "running", "completed", "failed"]


class AnalysisStreamResult(BaseModel):
    """Terminal payload returned to the frontend when analysis completes."""

    report_id: str
    status: str
    final_decision: str = ""
    quant_analysis: dict[str, Any] = Field(default_factory=dict)
    news_sentiment: dict[str, Any] = Field(default_factory=dict)
    social_sentiment: dict[str, Any] = Field(default_factory=dict)
    reports: dict[str, str | None] = Field(default_factory=dict)


class AnalysisStreamEvent(BaseModel):
    """Normalized public event sent over SSE to the frontend."""

    event_id: str
    sequence: int
    run_id: str
    timestamp: str
    type: AnalysisEventType
    stage: AnalysisStage
    status: AnalysisEventStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
