from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import app.news.generate_report as news_generate_report


class _FakeLLM:
    def invoke(self, messages):  # noqa: D401
        return SimpleNamespace(
            content=(
                '{"bias":"bullish","key_points":["Demand remains strong","Analysts raised targets"],'
                '"prediction_insights":"Prediction markets still lean positive."}'
            )
        )


def test_generate_report_includes_markdown_report(tmp_path, monkeypatch):
    search_payload = {
        "source": "tavily",
        "articles": [
            {
                "title": "NVDA demand keeps accelerating",
                "url": "https://example.com/nvda",
                "source": "Reuters",
                "published_time": "2026-04-02T08:00:00Z",
                "snippet": "Data-center demand stayed firm.",
            }
        ],
    }
    polymarket_payload = {
        "query": "NVDA",
        "markets_found": 1,
        "markets": [
            {
                "question": "Will NVDA rise this month?",
                "probability_yes": 0.61,
                "probability_no": 0.39,
                "volume_total": 1200000,
            }
        ],
    }

    monkeypatch.setattr(
        news_generate_report,
        "search_realtime_news",
        SimpleNamespace(invoke=lambda payload: json.dumps(search_payload)),
    )
    monkeypatch.setattr(
        news_generate_report,
        "search_polymarket_predictions",
        SimpleNamespace(invoke=lambda payload: json.dumps(polymarket_payload)),
    )
    monkeypatch.setattr(news_generate_report, "create_llm", lambda: _FakeLLM())

    report = news_generate_report.generate_report("NVDA", str(tmp_path))

    assert report["bias"] == "bullish"
    assert "# Macro News Sentiment Report" in report["markdown_report"]
    assert "NVDA demand keeps accelerating" in report["markdown_report"]
    assert "Will NVDA rise this month?" in report["markdown_report"]

    saved = json.loads(Path(tmp_path, "news.json").read_text(encoding="utf-8"))
    assert saved["markdown_report"] == report["markdown_report"]
