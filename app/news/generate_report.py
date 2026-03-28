"""News module unified report generator.

Exposes:
    generate_report(asset: str, run_dir: str) -> dict

The output is structured JSON in English for agent-to-agent consumption.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm_config import create_llm
from app.polymarket.tools import search_polymarket_predictions
from app.reporting.writer import write_json
from app.tools.local_tools import search_realtime_news

load_dotenv()


BiasLabel = Literal["bullish", "bearish", "neutral"]


class NewsBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    bias: BiasLabel
    key_points: List[str]
    prediction_insights: str
    sources: List[Dict[str, Any]]
    polymarket_markets: List[Dict[str, Any]]
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


def generate_report(asset: str, run_dir: str) -> NewsBundle:
    """Generate the News report and persist it as `news.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fetch sources using realtime search (Tavily first, DuckDuckGo fallback)
    search_result = search_realtime_news.invoke({"query": asset_norm, "limit": 8})
    search_data = json.loads(search_result) if isinstance(search_result, str) else search_result

    # Extract actual data source used (tavily or duckduckgo)
    actual_source = search_data.get("source", "unknown")

    # Extract articles from search result
    sources = [
        {
            "title": i.get("title"),
            "url": i.get("url"),
            "source": i.get("source"),
            "published_time": i.get("published_time"),
            "snippet": i.get("snippet"),
        }
        for i in search_data.get("articles", [])
        if isinstance(i, dict)
    ]

    # Fetch Polymarket prediction data
    polymarket_markets = None
    try:
        polymarket_data = search_polymarket_predictions.invoke({"query": asset_norm, "limit": 5})
        polymarket_markets = json.loads(polymarket_data) if polymarket_data else None
    except Exception as e:
        from logging import getLogger

        logger = getLogger(__name__)
        logger.warning(f"Failed to fetch Polymarket data: {e}")
        polymarket_markets = None

    system = (
        "You are a macro news sentiment analyst. Given news headlines/snippets and "
        "prediction market data from Polymarket about an asset, produce a strict JSON object.\n"
        "Constraints:\n"
        "- bias must be one of: bullish, bearish, neutral\n"
        "- key_points must be a list of 3-6 short bullet-like strings\n"
        "- prediction_insights: 1-2 sentences on what prediction markets suggest (or empty string if no data)\n"
        "- Output ONLY JSON."
    )

    prompt_parts = [f"Asset: {asset_norm}\n\n"]
    prompt_parts.append(f"News items (JSON):\n{json.dumps(sources, ensure_ascii=False)}\n")

    if polymarket_markets and polymarket_markets.get("markets_found", 0) > 0:
        prompt_parts.append(
            f"\nPolymarket prediction markets (JSON):\n{json.dumps(polymarket_markets, ensure_ascii=False)}\n"
        )
        prompt_parts.append(
            "\nConsider both news sentiment and prediction market probabilities in your analysis."
        )

    prompt = "".join(prompt_parts)

    llm = create_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = cast(str, getattr(resp, "content", "") or "").strip()

    # Best-effort parse: require JSON object.
    obj = _extract_json_object(content)
    bias = cast(BiasLabel, obj.get("bias", "neutral"))
    key_points_raw = obj.get("key_points")
    key_points = key_points_raw if isinstance(key_points_raw, list) else []

    report: Dict[str, Any] = {
        "asset": asset_norm,
        "module": "news",
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source": actual_source,  # Dynamic: tavily or duckduckgo
            "time_window_days": 7,
            "polymarket_enabled": polymarket_markets is not None
            and polymarket_markets.get("markets_found", 0) > 0,
        },
        "bias": bias if bias in ("bullish", "bearish", "neutral") else "neutral",
        "key_points": [str(x).strip() for x in key_points if isinstance(x, str) and x.strip()][:6],
        "prediction_insights": obj.get("prediction_insights", ""),
        "sources": sources,
        "polymarket_markets": polymarket_markets.get("markets", []) if polymarket_markets else [],
    }

    path = out_dir / "news.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return cast(NewsBundle, report)
