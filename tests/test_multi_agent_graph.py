"""Structure tests for multi-agent graph (no LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import app.graph_multi as graph_multi
from app.graph_multi import build_multi_agent_graph
from app.state import AgentState


def test_agent_state_typed_dict() -> None:
    s: AgentState = {"query": "test"}
    assert s["query"] == "test"


def test_build_multi_agent_graph_compiles() -> None:
    g = build_multi_agent_graph()
    assert g is not None
    # CompiledStateGraph has invoke
    assert hasattr(g, "invoke")


def test_cio_node_uses_structured_quant_prompt_and_writes_report_json(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class FakeLLM:
        def invoke(self, messages, config=None):
            captured["messages"] = messages
            return SimpleNamespace(content="CIO final decision")

    monkeypatch.setattr(graph_multi, "create_llm", lambda: FakeLLM())

    state: AgentState = {
        "query": "Analyze NVDA",
        "run_id": "20260402_100000",
        "run_dir": str(tmp_path),
        "quant_report_obj": {
            "asset": "NVDA",
            "trend": "bearish",
            "summary": "Technical summary",
            "markdown_report": (
                "# Quantitative Technical Report\n\n"
                "## ML Signal Governance\n"
                "- **Policy**: `event_driven_only`\n"
                "- **Requested symbol OOS**: AUC `0.5259`\n"
            ),
            "levels": {"support": 167.0, "resistance": 178.5},
            "indicators": {
                "last_close": 165.1,
                "sma_20": 178.5,
                "macd_line": -4.0,
                "macd_signal": -2.5,
                "macd_histogram": -1.4,
                "price_change_pct": -8.9,
            },
            "ml_quant": {
                "model": "lightgbm_panel",
                "target": "future_3d_up_big_move_gt_2pct_panel",
                "prob_up": 0.55,
                "final_prob_up": 0.5,
                "prediction": "up_big_move",
                "final_prediction": "event_driven_only",
                "ml_policy": "event_driven_only",
                "metrics": {
                    "requested_symbol_auc": 0.5259,
                    "requested_symbol_accuracy": 0.4397,
                    "requested_symbol_eval_rows": 1285,
                },
                "signal_filter": {
                    "alignment": "confirmed",
                    "position_multiplier": 0.0,
                    "historical_matches": 8,
                },
            },
        },
        "news_report_obj": {
            "module": "news",
            "summary": "Macro headline",
            "markdown_report": "# Macro News Sentiment Report\n\n- **Bias**: `bullish`\n",
        },
        "social_report_obj": {
            "module": "social",
            "summary": "Retail chatter",
            "markdown_report": "# Social Retail Sentiment Report\n\n- **Sentiment**: `bullish`\n",
        },
        "quant_report_path": str(tmp_path / "quant.json"),
        "news_report_path": str(tmp_path / "news.json"),
        "social_report_path": str(tmp_path / "social.json"),
    }

    result = graph_multi._cio_node(state)

    human_message = captured["messages"][1]
    content = str(getattr(human_message, "content", ""))
    assert "## ML Signal Governance" in content
    assert "`event_driven_only`" in content
    assert "AUC `0.5259`" in content
    assert "[Macro news sentiment report]" in content
    assert "**Bias**: `bullish`" in content
    assert "[Social retail sentiment report]" in content
    assert "**Sentiment**: `bullish`" in content

    cio_path = tmp_path / "cio.json"
    report_path = tmp_path / "report.json"
    assert cio_path.exists()
    assert report_path.exists()
    assert result["cio_report_path"] == str(cio_path)
    assert result["report_path"] == str(report_path)

    report_obj = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_obj["symbol"] == "NVDA"
    assert report_obj["asset_type"] == "stocks"
    assert report_obj["query"] == "Analyze NVDA"
    assert report_obj["quant_analysis"]["ml_quant"]["ml_policy"] == "event_driven_only"
    assert report_obj["final_decision"] == "CIO final decision"
    assert report_obj["reports"]["cio"] == "CIO final decision"
    assert report_obj["reports"]["quant"].startswith("# Quantitative Technical Report")
    assert report_obj["report_paths"]["cio"] == str(cio_path)
    assert report_obj["report_paths"]["aggregate"] == str(report_path)
