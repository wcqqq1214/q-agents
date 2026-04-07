"""Tests for the analysis runtime coordinator."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
from typing import Any


class _ImmediateLoop:
    """Minimal loop stub that executes callbacks synchronously."""

    def __init__(self) -> None:
        self.closed = False

    def call_soon_threadsafe(self, callback, *args: Any) -> None:
        if self.closed:
            raise RuntimeError("Event loop is closed")
        callback(*args)


def _load_runtime_module():
    spec = importlib.util.find_spec("app.analysis.runtime")
    assert spec is not None
    return importlib.import_module("app.analysis.runtime")


def test_runtime_drops_late_loop_emissions_after_close() -> None:
    """Late worker-thread emissions should not crash a closed public stream."""

    runtime_module = _load_runtime_module()
    runtime_cls = getattr(runtime_module, "AnalysisRuntime", None)
    assert runtime_cls is not None

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime = runtime_cls(run_id="run-1", loop=_ImmediateLoop(), public_queue=queue, db_path=None)

    close_public_stream = getattr(runtime, "close_public_stream", None)
    assert callable(close_public_stream)
    close_public_stream()

    runtime.emit_stage("news", "running", "Calling realtime news search")
    assert queue.empty()


def test_runtime_emits_terminal_event_only_once() -> None:
    """Only the first terminal event should reach the public queue."""

    runtime_module = _load_runtime_module()
    runtime_cls = getattr(runtime_module, "AnalysisRuntime", None)
    assert runtime_cls is not None

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime = runtime_cls(run_id="run-1", loop=_ImmediateLoop(), public_queue=queue, db_path=None)

    runtime.emit_result({"report_id": "run-1", "status": "completed", "final_decision": "done"})
    runtime.emit_error("cio", "should be ignored")

    first = queue.get_nowait()
    assert first["type"] == "result"
    assert first["data"]["report_id"] == "run-1"

    try:
        extra = queue.get_nowait()
    except asyncio.QueueEmpty:
        extra = None

    assert extra is None
