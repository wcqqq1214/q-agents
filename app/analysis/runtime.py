"""Runtime coordination for streamed analysis progress."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from app.api.models.analysis_events import (
    AnalysisEventStatus,
    AnalysisEventType,
    AnalysisStage,
    AnalysisStreamEvent,
)
from app.database.agent_history import save_analysis_progress_event, save_private_reasoning

logger = logging.getLogger(__name__)


class PrivateReasoningPayload(TypedDict, total=False):
    """Versioned internal-only reasoning envelope."""

    schema_version: int
    reasoning_kind: str
    model: str
    prompt: str
    raw_completion: str
    parsed_summary: dict[str, Any]
    tool_context: dict[str, Any]


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_private_reasoning_payload(payload: dict[str, Any]) -> PrivateReasoningPayload:
    """Validate the minimum contract for private reasoning persistence."""

    schema_version = payload.get("schema_version")
    reasoning_kind = payload.get("reasoning_kind")
    if not isinstance(schema_version, int):
        raise ValueError("private reasoning payload requires integer schema_version")
    if not isinstance(reasoning_kind, str) or not reasoning_kind.strip():
        raise ValueError("private reasoning payload requires non-empty reasoning_kind")
    return PrivateReasoningPayload(**payload)


class AnalysisRuntime:
    """Coordinate public telemetry and private reasoning for one analysis run."""

    def __init__(
        self,
        run_id: str,
        *,
        loop: Any | None = None,
        public_queue: Any | None = None,
        db_path: str | None = None,
    ) -> None:
        self.run_id = run_id
        self._loop = loop
        self._public_queue = public_queue
        self._db_path = db_path
        self._sequence = 0
        self._public_stream_closed = False
        self._terminal_emitted = False
        self._lock = threading.Lock()

    def close_public_stream(self) -> None:
        """Stop publishing any additional public events."""

        self._public_stream_closed = True

    def bind_run_id(self, run_id: str) -> None:
        """Update the runtime run id once the canonical run context exists."""

        if run_id:
            self.run_id = run_id

    def emit_stage(
        self,
        stage: AnalysisStage,
        status: AnalysisEventStatus,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a stage-level progress event."""

        self._emit_public(
            event_type="stage",
            stage=stage,
            status=status,
            message=message,
            data=data,
        )

    def emit_tool_call(
        self,
        stage: AnalysisStage,
        tool_name: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a user-visible tool-call start event."""

        payload = {"tool": tool_name, **(data or {})}
        self._emit_public(
            event_type="tool_call",
            stage=stage,
            status="running",
            message=message,
            data=payload,
        )

    def emit_tool_result(
        self,
        stage: AnalysisStage,
        tool_name: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a user-visible tool-call completion event."""

        payload = {"tool": tool_name, **(data or {})}
        self._emit_public(
            event_type="tool_result",
            stage=stage,
            status="completed",
            message=message,
            data=payload,
        )

    def emit_result(self, payload: dict[str, Any]) -> None:
        """Emit the terminal success event once."""

        self._emit_public(
            event_type="result",
            stage="cio",
            status="completed",
            message="Analysis complete",
            data=payload,
            terminal=True,
        )

    def emit_error(
        self,
        stage: AnalysisStage,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit the terminal error event once."""

        self._emit_public(
            event_type="error",
            stage=stage,
            status="failed",
            message=message,
            data=data,
            terminal=True,
        )

    def record_private_reasoning(
        self,
        stage: AnalysisStage,
        agent_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist internal-only reasoning payloads after validation."""

        if self._db_path is None:
            return
        validated = _validate_private_reasoning_payload(payload)
        save_private_reasoning(
            reasoning_id=f"rsn_{uuid.uuid4().hex}",
            run_id=self.run_id,
            stage=stage,
            agent_type=agent_type,
            payload=dict(validated),
            created_at=datetime.now(timezone.utc),
            db_path=self._db_path,
        )

    def _emit_public(
        self,
        *,
        event_type: AnalysisEventType,
        stage: AnalysisStage,
        status: AnalysisEventStatus,
        message: str,
        data: dict[str, Any] | None = None,
        terminal: bool = False,
    ) -> None:
        with self._lock:
            if terminal and self._terminal_emitted:
                return
            if terminal:
                self._terminal_emitted = True

            self._sequence += 1
            event = AnalysisStreamEvent(
                event_id=f"evt_{self._sequence:06d}",
                sequence=self._sequence,
                run_id=self.run_id,
                timestamp=_utc_now_iso(),
                type=event_type,
                stage=stage,
                status=status,
                message=message,
                data=data or {},
            ).model_dump(mode="json")

        if self._db_path is not None:
            save_analysis_progress_event(
                event_id=event["event_id"],
                run_id=self.run_id,
                sequence=event["sequence"],
                stage=stage,
                event_type=event_type,
                status=status,
                message=message,
                timestamp=datetime.now(timezone.utc),
                data=event["data"],
                db_path=self._db_path,
            )

        self._publish_to_public_queue(event)

    def _publish_to_public_queue(self, event: dict[str, Any]) -> None:
        if self._public_stream_closed or self._loop is None or self._public_queue is None:
            return

        loop_is_closed = getattr(self._loop, "is_closed", None)
        if callable(loop_is_closed) and loop_is_closed():
            self._public_stream_closed = True
            return
        if getattr(self._loop, "closed", False):
            self._public_stream_closed = True
            return

        try:
            self._loop.call_soon_threadsafe(self._public_queue.put_nowait, event)
        except RuntimeError:
            self._public_stream_closed = True
            logger.info("Dropped late analysis event after loop shutdown for run %s", self.run_id)
