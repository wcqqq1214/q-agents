from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import app.quant.generate_report as quant_generate_report


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def invoke(self, messages):  # noqa: D401
        content = self._responses.pop(0) if self._responses else ""
        return SimpleNamespace(content=content)


def _fake_ml_quant() -> dict:
    return {
        "model": "lightgbm_panel",
        "target": "future_3d_up_big_move_gt_2pct_panel",
        "prob_up": 0.54,
        "final_prob_up": 0.5,
        "prediction": "up_big_move",
        "final_prediction": "event_driven_only",
        "ml_policy": "event_driven_only",
        "signal_filter": {
            "alignment": "confirmed",
            "position_multiplier": 0.0,
            "ml_policy": "event_driven_only",
        },
        "metrics": {
            "requested_symbol_auc": 0.52,
            "requested_symbol_accuracy": 0.44,
        },
    }


def test_generate_report_retries_llm_summary_before_fallback(tmp_path, monkeypatch):
    indicators = {
        "ticker": "NVDA",
        "last_close": 120.0,
        "sma_20": 110.0,
        "macd_line": 1.5,
        "macd_signal": 1.0,
        "bb_lower": 102.0,
        "bb_upper": 125.0,
        "price_change_pct": 6.0,
    }

    monkeypatch.setattr(
        quant_generate_report,
        "get_local_stock_data",
        SimpleNamespace(invoke=lambda payload: json.dumps(indicators)),
    )
    monkeypatch.setattr(
        quant_generate_report,
        "create_llm",
        lambda: _FakeLLM(
            [
                "not-json",
                '{"trend":"bullish","levels":{"support":108.0,"resistance":126.0},"summary":"Momentum improved after a brief parser retry."}',
            ]
        ),
    )
    monkeypatch.setattr(
        quant_generate_report,
        "run_ml_quant_analysis",
        SimpleNamespace(invoke=lambda payload: _fake_ml_quant()),
    )

    report = quant_generate_report.generate_report("NVDA", str(tmp_path))

    assert report["trend"] == "bullish"
    assert report["levels"]["support"] == 108.0
    assert report["summary"] == "Momentum improved after a brief parser retry."
    assert report["ml_quant"]["ml_policy"] == "event_driven_only"
    assert Path(tmp_path, "quant.json").exists()


def test_generate_report_falls_back_to_rules_when_llm_summary_stays_invalid(tmp_path, monkeypatch):
    indicators = {
        "ticker": "NVDA",
        "last_close": 95.0,
        "sma_20": 110.0,
        "macd_line": -2.0,
        "macd_signal": -1.0,
        "bb_lower": 90.0,
        "bb_upper": 118.0,
        "price_change_pct": -8.0,
    }

    monkeypatch.setattr(
        quant_generate_report,
        "get_local_stock_data",
        SimpleNamespace(invoke=lambda payload: json.dumps(indicators)),
    )
    monkeypatch.setattr(
        quant_generate_report,
        "create_llm",
        lambda: _FakeLLM(["not-json", "still not-json"]),
    )
    monkeypatch.setattr(
        quant_generate_report,
        "run_ml_quant_analysis",
        SimpleNamespace(invoke=lambda payload: _fake_ml_quant()),
    )

    report = quant_generate_report.generate_report("NVDA", str(tmp_path))

    assert report["trend"] == "bearish"
    assert report["levels"]["support"] == 90.0
    assert report["levels"]["resistance"] == 118.0
    assert "fallback technical view" in report["summary"]
    assert report["ml_quant"]["final_prediction"] == "event_driven_only"
    saved = json.loads(Path(tmp_path, "quant.json").read_text(encoding="utf-8"))
    assert saved["ml_quant"]["ml_policy"] == "event_driven_only"
