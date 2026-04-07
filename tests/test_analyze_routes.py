"""Tests for analysis routes."""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from app.api.main import app

    return TestClient(app)


@pytest.fixture
def mock_run_once():
    """Mock the graph_multi.run_once function."""
    return Mock(
        return_value={
            "run_id": "20260321_120000_AAPL",
            "run_dir": "/tmp/test_run",
            "final_decision": "Test analysis result",
            "cio_report_path": "/tmp/test_run/cio.json",
        }
    )


class TestAnalyzeStream:
    """Tests for GET /api/analyze/stream endpoint."""

    def test_stream_emits_progress_before_final_result(self, client):
        """The stream should emit visible progress before the final CIO payload."""
        mock_result = {
            "run_id": "20260321_120000_TEST",
            "run_dir": "/tmp/test_run",
            "final_decision": "# Test Report\n\nThis is a **test** analysis.",
            "quant_report_obj": {"price": 150.0},
            "news_report_obj": {"sentiment": "positive"},
            "social_report_obj": {"sentiment": "bullish"},
            "cio_report_path": "/tmp/test_run/cio.json",
        }

        def fake_run_once(query: str, runtime=None):
            assert query == "TEST"
            assert runtime is not None
            runtime.emit_stage("news", "running", "Calling realtime news search")
            runtime.emit_tool_result(
                "news",
                "search_realtime_news",
                "Fetched 8 news articles from Tavily",
                {"provider": "tavily", "article_count": 8},
            )
            return mock_result

        with patch("app.api.routes.analyze.run_once", side_effect=fake_run_once):
            with client.stream("GET", "/api/analyze/stream?query=TEST") as response:
                assert response.status_code == 200

                # Collect all events
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        events.append(data)

                progress_events = [
                    e for e in events if e.get("type") in {"stage", "tool_call", "tool_result"}
                ]
                assert progress_events
                assert progress_events[0]["stage"] == "news"
                assert progress_events[0]["message"] == "Calling realtime news search"

                result_events = [e for e in events if e.get("type") == "result"]
                assert len(result_events) == 1
                assert events.index(progress_events[0]) < events.index(result_events[0])

                result_data = result_events[0]["data"]
                assert result_data["report_id"] == "20260321_120000_TEST"
                assert result_data["status"] == "completed"
                assert (
                    result_data["final_decision"] == "# Test Report\n\nThis is a **test** analysis."
                )

    def test_stream_emits_error_event_when_background_run_fails(self, client):
        """The stream should keep partial progress and then terminate with an error event."""

        def fake_run_once(query: str, runtime=None):
            assert query == "AAPL"
            assert runtime is not None
            runtime.emit_stage("quant", "running", "Loading 90-day local technical snapshot")
            raise Exception("Test error")

        with patch("app.api.routes.analyze.run_once", side_effect=fake_run_once):
            with client.stream("GET", "/api/analyze/stream?query=AAPL") as response:
                assert response.status_code == 200

                # Collect all events
                events = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        events.append(data)

                progress_events = [
                    e for e in events if e.get("type") in {"stage", "tool_call", "tool_result"}
                ]
                assert progress_events
                assert progress_events[0]["stage"] == "quant"

                error_events = [e for e in events if e.get("type") == "error"]
                assert len(error_events) == 1
                assert events.index(progress_events[0]) < events.index(error_events[0])
                assert "Test error" in error_events[0]["message"]
