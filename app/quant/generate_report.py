"""Quant module unified report generator.

Exposes:
    generate_report(asset: str, run_dir: str) -> dict

The output is structured JSON in English for agent-to-agent consumption.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm_config import create_llm
from app.reporting.writer import write_json
from app.tools.finance_tools import get_stock_data
from app.tools.quant_tool import run_ml_quant_analysis


load_dotenv()


TrendLabel = Literal["bullish", "bearish", "neutral"]


class QuantBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    trend: TrendLabel
    indicators: Dict[str, Any]
    levels: Dict[str, Any]
    summary: str
    report_path: str


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from a possibly noisy model output."""

    raw = (text or "").strip()
    if raw.startswith("{") and raw.endswith("}"):
        return cast(Dict[str, Any], json.loads(raw))

    def _balanced_candidates(s: str) -> list[str]:
        out: list[str] = []
        start_positions = [i for i, ch in enumerate(s) if ch == "{"]
        for start in start_positions:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                else:
                    if ch == '"':
                        in_str = True
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            out.append(s[start : i + 1])
                            break
        return out

    for cand in _balanced_candidates(raw):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return cast(Dict[str, Any], obj)
        except Exception:
            continue
    raise ValueError("No valid JSON object found in model output.")


def generate_report(asset: str, run_dir: str) -> QuantBundle:
    """Generate the Quant report and persist it as `quant.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tool provides compact JSON string of indicators.
    indicators_json = cast(str, get_stock_data.invoke({"ticker": asset_norm, "period": "3mo"}))
    try:
        indicators = cast(Dict[str, Any], json.loads(indicators_json))
    except Exception:
        indicators = {"raw": indicators_json}

    system = (
        "You are a technical analyst. Given an indicators snapshot JSON, produce a strict JSON object with keys:\n"
        "- trend: bullish|bearish|neutral\n"
        "- levels: {support: number|null, resistance: number|null}\n"
        "- summary: one English sentence (<= 25 words)\n"
        "Output ONLY JSON."
    )
    prompt = f"Asset: {asset_norm}\nIndicators JSON:\n{json.dumps(indicators, ensure_ascii=False)}\n"

    llm = create_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = cast(str, getattr(resp, "content", "") or "").strip()
    obj = _extract_json_object(content)

    trend = obj.get("trend", "neutral")
    if trend not in ("bullish", "bearish", "neutral"):
        trend = "neutral"

    levels_raw = obj.get("levels")
    levels = levels_raw if isinstance(levels_raw, dict) else {}
    summary = obj.get("summary")
    summary_str = str(summary).strip() if isinstance(summary, str) and summary.strip() else ""

    # Run the ML quant analysis tool to enrich the bundle with an ml_quant block.
    try:
        ml_quant_raw = run_ml_quant_analysis.invoke({"ticker": asset_norm})
        ml_quant = cast(Dict[str, Any], ml_quant_raw if isinstance(ml_quant_raw, dict) else {})
    except Exception as exc:
        ml_quant = {
            "model": "lightgbm",
            "target": "next_day_direction",
            "data_source": "yfinance_direct",
            "error": f"Failed to run ML quant analysis: {type(exc).__name__}: {exc}",
        }

    report: Dict[str, Any] = {
        "asset": asset_norm,
        "module": "quant",
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source": "yfinance_mcp",
        },
        "trend": cast(TrendLabel, trend),
        "indicators": indicators,
        "levels": {
            "support": levels.get("support"),
            "resistance": levels.get("resistance"),
        },
        "summary": summary_str,
        "ml_quant": ml_quant,
    }

    path = out_dir / "quant.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return cast(QuantBundle, report)

