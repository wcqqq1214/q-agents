"""News module unified report generator.

Exposes:
    generate_report(asset: str, run_dir: str) -> dict

The output is structured JSON in English for agent-to-agent consumption.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.reporting.writer import write_json
from app.tools.finance_tools import search_financial_news


load_dotenv()


BiasLabel = Literal["bullish", "bearish", "neutral"]


class NewsBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    bias: BiasLabel
    key_points: List[str]
    sources: List[Dict[str, Any]]
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


def _make_minimax_llm() -> ChatOpenAI:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY is not set. Add it to .env before running reports.")
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    common: Dict[str, Any] = {"temperature": 0.0}
    # langchain-openai 参数名在不同版本间有差异；这里做运行时兼容初始化。
    try:
        return ChatOpenAI(**{"model": model, "api_key": api_key, "base_url": base_url, **common})
    except TypeError:
        return ChatOpenAI(
            **{
                "model_name": model,
                "openai_api_key": api_key,
                "openai_api_base": base_url,
                **common,
            }
        )


def generate_report(asset: str, run_dir: str) -> NewsBundle:
    """Generate the News report and persist it as `news.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fetch sources first (tool call, deterministic).
    items = search_financial_news.invoke({"query": asset_norm, "limit": 8})
    sources = [
        {
            "title": i.get("title"),
            "url": i.get("url"),
            "source": i.get("source"),
            "published_time": i.get("published_time"),
            "snippet": i.get("snippet"),
        }
        for i in (items or [])
        if isinstance(i, dict)
    ]

    system = (
        "You are a macro news sentiment analyst. Given a list of recent headlines/snippets about an asset, "
        "produce a strict JSON object with keys: bias, key_points, sources_used_count.\n"
        "Constraints:\n"
        "- bias must be one of: bullish, bearish, neutral\n"
        "- key_points must be a list of 3-6 short bullet-like strings\n"
        "- Output ONLY JSON."
    )
    prompt = (
        f"Asset: {asset_norm}\n\n"
        f"News items (JSON):\n{json.dumps(sources, ensure_ascii=False)}\n"
    )

    llm = _make_minimax_llm()
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
            "source": "duckduckgo",
        },
        "bias": bias if bias in ("bullish", "bearish", "neutral") else "neutral",
        "key_points": [str(x).strip() for x in key_points if isinstance(x, str) and x.strip()][:6],
        "sources": sources,
    }

    path = out_dir / "news.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return cast(NewsBundle, report)

