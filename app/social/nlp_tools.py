"""LLM-driven NLP tools for Reddit retail sentiment analysis."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()


# Inter-agent structured data should be in English.
SentimentLabel = Literal["panic", "bearish", "neutral", "bullish", "euphoric"]


class SocialNlpResult(TypedDict):
    """Structured result schema for Social Agent NLP output."""

    sentiment: SentimentLabel
    keywords: List[str]
    summary: str


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*?\}", flags=re.MULTILINE)


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"{name} is not set. Add it to .env before using the social agent.")
    return v


def _make_minimax_llm() -> ChatOpenAI:
    """Create ChatOpenAI pointed at MiniMax OpenAI-compatible API."""

    api_key = _require_env("MINIMAX_API_KEY")
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    common: Dict[str, Any] = {"temperature": 0.0}
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


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from a model response."""

    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model response.")

    # Case 1: response is already pure JSON.
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return cast(Dict[str, Any], obj)
    except Exception:
        pass

    # Case 2: scan for the first valid {...} JSON object in the text.
    for m in _JSON_BLOCK_RE.finditer(raw):
        candidate = m.group(0)
        try:
            obj2 = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj2, dict):
            return cast(Dict[str, Any], obj2)

    raise ValueError("No valid JSON object found in model response.")


def _normalize_keywords(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for x in value:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    if isinstance(value, str):
        # Allow comma/Chinese comma separated fallback.
        parts = re.split(r"[，,]\s*", value.strip())
        return [p for p in (p.strip() for p in parts) if p]
    return []


def _validate_result(obj: Dict[str, Any]) -> SocialNlpResult:
    sentiment = obj.get("sentiment")
    keywords = _normalize_keywords(obj.get("keywords"))
    summary = obj.get("summary")

    allowed: List[str] = ["panic", "bearish", "neutral", "bullish", "euphoric"]
    if sentiment not in allowed:
        raise ValueError(f"Invalid sentiment={sentiment!r}. Must be one of {allowed}.")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be a non-empty string.")

    # Constrain sizes for downstream stability.
    keywords = keywords[:5]
    summary_clean = summary.strip()
    if len(summary_clean) > 300:
        summary_clean = summary_clean[:299] + "…"

    return SocialNlpResult(
        sentiment=cast(SentimentLabel, sentiment),
        keywords=keywords,
        summary=summary_clean,
    )


@tool("analyze_reddit_text")
def analyze_reddit_text(asset: str, text: str) -> SocialNlpResult:
    """Analyze Reddit discussion text into sentiment, keywords, and a short summary (strict JSON).

    This tool converts a cleaned Reddit corpus (typically produced by
    ``get_reddit_discussion``) into a compact, structured JSON-like object for
    the **Social Agent** and, ultimately, the CIO Agent to consume.

    The output schema is intentionally strict so that the downstream CIO
    aggregation step can treat it as structured data rather than natural
    language. The model is instructed to output **only** a JSON object with
    exactly three keys:

    - ``sentiment``: one of ``panic`` / ``bearish`` / ``neutral`` / ``bullish`` / ``euphoric``\n
    - ``keywords``: an array of 5 short keyword strings driving the sentiment\n
    - ``summary``: a single English sentence (<= 25 words preferred)\n

    Environment variables required:
        - ``MINIMAX_API_KEY`` (required)
        - ``MINIMAX_BASE_URL`` (optional, default: https://api.minimaxi.com/v1)
        - ``MINIMAX_MODEL`` (optional, default: MiniMax-M2.5)

    Args:
        asset: Asset identifier such as ``\"BTC\"`` or ``\"NVDA\"`` for labeling
            the analysis context.
        text: Cleaned discussion corpus string. This should already have URLs
            removed and be truncated to a safe size for the model context.

    Returns:
        A ``SocialNlpResult`` dictionary containing ``sentiment``, ``keywords``,
        and ``summary``.

    Raises:
        RuntimeError: If required environment variables are missing.
        ValueError: If the model output cannot be parsed into the required schema.
    """

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    text_norm = (text or "").strip()
    # Graceful degradation when Reddit ingestion returns no content
    # (for example, Reddit is unreachable in the current environment).
    if not text_norm or "No posts fetched from Reddit" in text_norm:
        return SocialNlpResult(
            sentiment=cast(SentimentLabel, "neutral"),
            keywords=[],
            summary="No Reddit discussion text was available in the last 24 hours; sentiment defaults to neutral.",
        )

    system = (
        "You are a professional quantitative finance and social sentiment analyst. "
        "You will receive a 24-hour Reddit retail discussion corpus about a single asset. "
        "Perform NLP analysis and output ONLY a strict JSON object. Do not output any extra text."
    )
    prompt = (
        f"Asset: {asset_norm}\n\n"
        "Return ONLY this JSON schema:\n"
        "{\n"
        '  \"sentiment\": \"panic|bearish|neutral|bullish|euphoric\",\n'
        '  \"keywords\": [\"...\", \"...\", \"...\", \"...\", \"...\"],\n'
        '  \"summary\": \"One English sentence summary (<= 25 words)\"\n'
        "}\n\n"
        "Discussion text:\n"
        f"{text_norm}\n"
    )

    llm = _make_minimax_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    content = cast(str, getattr(resp, "content", "") or "")

    obj = _extract_json_object(content)
    return _validate_result(obj)

