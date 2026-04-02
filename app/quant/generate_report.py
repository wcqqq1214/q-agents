"""Quant module unified report generator.

Exposes:
    generate_report(asset: str, run_dir: str) -> dict

The output is structured JSON in English for agent-to-agent consumption.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm_config import create_llm
from app.reporting.writer import write_json
from app.tools.local_tools import get_local_stock_data
from app.tools.quant_tool import run_ml_quant_analysis

load_dotenv()
logger = logging.getLogger(__name__)


TrendLabel = Literal["bullish", "bearish", "neutral"]


class QuantBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    trend: TrendLabel
    indicators: Dict[str, Any]
    levels: Dict[str, Any]
    summary: str
    ml_quant: Dict[str, Any]
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


def _safe_float(value: Any) -> float | None:
    """Return a float for numeric-like values; otherwise ``None``."""

    if isinstance(value, (int, float)):
        return float(value)
    return None


def _fallback_trend_from_indicators(indicators: Dict[str, Any]) -> TrendLabel:
    """Infer a coarse trend label directly from indicator values."""

    last_close = _safe_float(indicators.get("last_close"))
    sma_20 = _safe_float(indicators.get("sma_20"))
    macd_line = _safe_float(indicators.get("macd_line"))
    macd_signal = _safe_float(indicators.get("macd_signal"))

    bullish = (
        last_close is not None
        and sma_20 is not None
        and macd_line is not None
        and macd_signal is not None
        and last_close >= sma_20
        and macd_line >= macd_signal
    )
    bearish = (
        last_close is not None
        and sma_20 is not None
        and macd_line is not None
        and macd_signal is not None
        and last_close < sma_20
        and macd_line < macd_signal
    )
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "neutral"


def _fallback_levels_from_indicators(indicators: Dict[str, Any]) -> Dict[str, float | None]:
    """Infer simple support and resistance levels from available indicators."""

    support = _safe_float(indicators.get("bb_lower"))
    resistance = _safe_float(indicators.get("bb_upper"))
    if support is None:
        support = _safe_float(indicators.get("sma_20"))
    if resistance is None:
        resistance = _safe_float(indicators.get("sma_20"))
    return {"support": support, "resistance": resistance}


def _fallback_summary_from_indicators(asset: str, indicators: Dict[str, Any], trend: TrendLabel) -> str:
    """Build a deterministic English fallback summary from local indicators."""

    if "error" in indicators:
        return f"{asset} fallback summary: local technical snapshot unavailable; rely on raw quant indicators and ML block."

    price_relation = "near"  # Default keeps summary short if data is partial.
    last_close = _safe_float(indicators.get("last_close"))
    sma_20 = _safe_float(indicators.get("sma_20"))
    if last_close is not None and sma_20 is not None:
        if last_close > sma_20:
            price_relation = "above"
        elif last_close < sma_20:
            price_relation = "below"

    macd_line = _safe_float(indicators.get("macd_line"))
    macd_signal = _safe_float(indicators.get("macd_signal"))
    macd_bias = "mixed"
    if macd_line is not None and macd_signal is not None:
        macd_bias = "positive MACD" if macd_line >= macd_signal else "negative MACD"

    return f"{asset} fallback technical view: {trend}, price {price_relation} SMA20, {macd_bias}; check embedded ML block before trading."


def _summarize_quant_snapshot(asset: str, indicators: Dict[str, Any]) -> tuple[TrendLabel, Dict[str, Any], str]:
    """Produce a robust quant summary with retry and deterministic fallback."""

    system = (
        "You are a technical analyst. Given an indicators snapshot JSON, produce a strict JSON object with keys:\n"
        "- trend: bullish|bearish|neutral\n"
        "- levels: {support: number|null, resistance: number|null}\n"
        "- summary: one English sentence (<= 25 words)\n"
        "Output ONLY JSON."
    )
    base_prompt = (
        f"Asset: {asset}\nIndicators JSON:\n{json.dumps(indicators, ensure_ascii=False)}\n"
    )

    llm = create_llm()
    last_error: Exception | None = None

    for attempt in range(2):
        prompt = base_prompt
        if attempt > 0 and last_error is not None:
            prompt += (
                "\nYour previous response could not be parsed as the required JSON object.\n"
                f"Parser error: {type(last_error).__name__}: {last_error}\n"
                "Return ONLY valid JSON that matches the schema."
            )
        try:
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
            if not summary_str:
                summary_str = _fallback_summary_from_indicators(asset, indicators, cast(TrendLabel, trend))
            return cast(TrendLabel, trend), levels, summary_str
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    trend = _fallback_trend_from_indicators(indicators)
    levels = _fallback_levels_from_indicators(indicators)
    summary = _fallback_summary_from_indicators(asset, indicators, trend)
    if last_error is not None:
        logger.warning(
            "Quant summary generation fell back to deterministic rules for %s after parse failure: %s: %s",
            asset,
            type(last_error).__name__,
            last_error,
        )
    return trend, levels, summary


def generate_report(asset: str, run_dir: str) -> QuantBundle:
    """Generate the Quant report and persist it as `quant.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tool provides compact JSON string of indicators from local database
    indicators_json = cast(str, get_local_stock_data.invoke({"ticker": asset_norm, "days": 90}))
    try:
        indicators = cast(Dict[str, Any], json.loads(indicators_json))
    except Exception:
        indicators = {"raw": indicators_json}

    # Determine actual data source
    actual_source = "local_database" if "error" not in indicators else "unknown"

    trend, levels, summary_str = _summarize_quant_snapshot(asset_norm, indicators)

    # Run the ML quant analysis tool to enrich the bundle with an ml_quant block.
    try:
        ml_quant_raw = run_ml_quant_analysis.invoke({"ticker": asset_norm})
        ml_quant = cast(Dict[str, Any], ml_quant_raw if isinstance(ml_quant_raw, dict) else {})
    except Exception as exc:
        ml_quant = {
            "model": "lightgbm_panel",
            "target": "future_3d_up_big_move_gt_2pct_panel",
            "data_source": "sqlite_panel_db",
            "error": f"Failed to run ML quant analysis: {type(exc).__name__}: {exc}",
        }

    report: Dict[str, Any] = {
        "asset": asset_norm,
        "module": "quant",
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source": actual_source,  # Dynamic: local_database or unknown
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
