"""Stage-level event emission tests for analysis report generators."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app import graph_multi
from app.analysis import AnalysisRuntime
from app.news import generate_report as news_report_module
from app.quant import generate_report as quant_report_module
from app.social import generate_report as social_report_module


class _ImmediateLoop:
    """Minimal loop stub that executes queued callbacks immediately."""

    def call_soon_threadsafe(self, callback, *args: Any) -> None:
        callback(*args)


class _ToolStub:
    """Simple stand-in for tool objects exposing an invoke method."""

    def __init__(self, response: Any) -> None:
        self._response = response

    def invoke(self, payload: dict[str, Any]) -> Any:
        _ = payload
        return self._response


def _make_runtime() -> tuple[AnalysisRuntime, asyncio.Queue[dict[str, Any]]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    runtime = AnalysisRuntime(
        run_id="20260408_120000_TEST",
        loop=_ImmediateLoop(),
        public_queue=queue,
        db_path=None,
    )
    return runtime, queue


def _drain_queue(queue: asyncio.Queue[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return events


def test_quant_report_emits_indicator_and_ml_events(monkeypatch, tmp_path) -> None:
    """Quant report generation should publish indicator and ML progress events."""

    runtime, queue = _make_runtime()

    monkeypatch.setattr(
        quant_report_module,
        "get_local_stock_data",
        _ToolStub(
            json.dumps(
                {
                    "last_close": 123.45,
                    "sma_20": 120.0,
                    "macd_line": 2.5,
                    "macd_signal": 1.5,
                    "macd_histogram": 1.0,
                    "price_change_pct": 0.03,
                }
            )
        ),
    )
    monkeypatch.setattr(
        quant_report_module,
        "_summarize_quant_snapshot",
        lambda asset, indicators: (
            "bullish",
            {"support": 118.0, "resistance": 130.0},
            f"{asset} remains technically constructive.",
        ),
    )
    monkeypatch.setattr(
        quant_report_module,
        "run_ml_quant_analysis",
        _ToolStub(
            {
                "model": "lightgbm_panel",
                "target": "future_3d_up_big_move_gt_2pct_panel",
                "ml_policy": "event_driven_only",
                "prediction": "up",
                "prob_up": 0.71,
                "final_prediction": "up",
                "final_prob_up": 0.71,
            }
        ),
    )

    quant_report_module.generate_report("AAPL", str(tmp_path), runtime=runtime)
    events = _drain_queue(queue)

    messages = [event["message"] for event in events]
    assert "Loading 90-day local technical snapshot" in messages
    assert "Loaded technical snapshot from local database" in messages
    assert "Running ML quant analysis" in messages
    assert "Quant report completed" in messages
    assert any(
        event["type"] == "tool_result"
        and event["data"].get("tool") == "get_local_stock_data"
        and event["data"].get("source") == "local_database"
        for event in events
    )
    assert any(
        event["stage"] == "quant"
        and event["status"] == "completed"
        and event["message"] == "Quant report completed"
        for event in events
    )


def test_news_report_emits_news_fetch_and_polymarket_summary(monkeypatch, tmp_path) -> None:
    """News report generation should publish provider and article-count telemetry."""

    runtime, queue = _make_runtime()

    monkeypatch.setattr(
        news_report_module,
        "search_realtime_news",
        _ToolStub(
            json.dumps(
                {
                    "source": "tavily",
                    "articles": [
                        {
                            "title": f"Headline {index}",
                            "url": f"https://example.com/{index}",
                            "source": "Example",
                            "published_time": "2026-04-08T12:00:00Z",
                            "snippet": "Snippet",
                        }
                        for index in range(8)
                    ],
                }
            )
        ),
    )
    monkeypatch.setattr(
        news_report_module,
        "search_polymarket_predictions",
        _ToolStub(
            json.dumps(
                {
                    "markets_found": 1,
                    "markets": [
                        {
                            "question": "Will NVDA finish green this week?",
                            "probability_yes": 0.58,
                            "probability_no": 0.42,
                            "volume_total": 12345,
                        }
                    ],
                }
            )
        ),
    )

    class _FakeLlm:
        def invoke(self, messages: list[object]) -> object:
            return type(
                "_Response",
                (),
                {
                    "content": json.dumps(
                        {
                            "bias": "bullish",
                            "key_points": ["Demand remains strong", "AI spend is resilient"],
                            "prediction_insights": "Prediction markets lean modestly bullish.",
                        }
                    )
                },
            )()

    monkeypatch.setattr(news_report_module, "create_llm", lambda: _FakeLlm())

    news_report_module.generate_report("NVDA", str(tmp_path), runtime=runtime)
    events = _drain_queue(queue)

    messages = [event["message"] for event in events]
    assert "Calling realtime news search" in messages
    assert "Fetched 8 news articles from Tavily" in messages
    assert "Fetching Polymarket signals" in messages
    assert "News sentiment report completed" in messages
    assert any(
        event["type"] == "tool_result"
        and event["data"].get("tool") == "search_realtime_news"
        and event["data"].get("provider") == "tavily"
        and event["data"].get("article_count") == 8
        for event in events
    )
    assert any(
        event["stage"] == "news"
        and event["status"] == "completed"
        and event["message"] == "News sentiment report completed"
        for event in events
    )


def test_social_report_emits_fetch_and_nlp_summary(monkeypatch, tmp_path) -> None:
    """Social report generation should publish Reddit fetch and NLP telemetry."""

    runtime, queue = _make_runtime()

    monkeypatch.setattr(
        social_report_module,
        "get_reddit_discussion",
        _ToolStub("Asset: NVDA\nSource: reddit\nWindow: 24h\nPostCount: 23\nCommentCount: 184\n"),
    )
    monkeypatch.setattr(
        social_report_module,
        "analyze_reddit_text",
        _ToolStub(
            {
                "sentiment": "bullish",
                "keywords": ["AI", "earnings"],
                "summary": "Retail remains constructive.",
                "signal_available": True,
                "coverage_status": "available",
            }
        ),
    )
    monkeypatch.setattr(
        social_report_module,
        "build_social_report",
        _ToolStub(
            {
                "asset": "NVDA",
                "sentiment": "bullish",
                "keywords": ["AI", "earnings"],
                "summary": "Retail remains constructive.",
                "signal_available": True,
                "coverage_status": "available",
                "meta": {
                    "source": "reddit",
                    "window": "24h",
                    "post_count": 23,
                    "comment_count": 184,
                    "subreddits": ["stocks", "wallstreetbets"],
                },
            }
        ),
    )

    social_report_module.generate_report("NVDA", str(tmp_path), runtime=runtime)
    events = _drain_queue(queue)

    messages = [event["message"] for event in events]
    assert "Fetching Reddit discussion" in messages
    assert "Fetched 23 Reddit posts and 184 comments" in messages
    assert "Running social sentiment analysis" in messages
    assert "Social report completed" in messages
    assert any(
        event["type"] == "tool_result"
        and event["data"].get("tool") == "get_reddit_discussion"
        and event["data"].get("post_count") == 23
        and event["data"].get("comment_count") == 184
        for event in events
    )
    assert any(
        event["stage"] == "social"
        and event["status"] == "completed"
        and event["message"] == "Social report completed"
        for event in events
    )


def test_cio_node_emits_stage_start_then_completion(monkeypatch, tmp_path) -> None:
    """CIO synthesis should expose sanitized stage progress before returning."""

    runtime, queue = _make_runtime()

    class _FakeLlm:
        def invoke(self, messages: list[object], config=None) -> object:
            _ = messages, config
            return type("_Response", (), {"content": "Final CIO decision"})()

    monkeypatch.setattr(graph_multi, "create_llm", lambda: _FakeLlm())

    state = {
        "query": "Analyze NVDA",
        "run_dir": str(tmp_path),
        "quant_report_obj": {
            "asset": "NVDA",
            "markdown_report": "# Quantitative Technical Report\nBullish",
        },
        "news_report_obj": {
            "asset": "NVDA",
            "markdown_report": "# Macro News Sentiment Report\nBullish",
        },
        "social_report_obj": {
            "asset": "NVDA",
            "markdown_report": "# Social Retail Sentiment Report\nBullish",
        },
    }

    result = graph_multi._cio_node(state, runtime=runtime)
    events = _drain_queue(queue)

    messages = [event["message"] for event in events]
    assert "CIO synthesis started" in messages
    assert "CIO synthesis completed" in messages
    assert result["final_decision"] == "Final CIO decision"
