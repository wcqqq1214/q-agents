"""Entry point for calling the Social Agent from CIO/orchestrators."""

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict, cast

from langchain_core.runnables import RunnableConfig


class SocialReport(TypedDict, total=False):
    """Unified Social Agent report returned to CIO."""

    sentiment: str
    keywords: list[str]
    summary: str
    report_path: str
    asset: str
    meta: Dict[str, Any]


def _extract_ingest_meta_from_text(text: str) -> Dict[str, Any]:
    """Extract ingestion meta from the header lines of get_reddit_discussion output."""

    meta_raw: Dict[str, str] = {}
    for line in (text or "").splitlines()[:20]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip()
        if key in {"Asset", "Window", "Subreddits", "Source", "PostCount", "CommentCount", "GeneratedAt(UTC)"}:
            meta_raw[key] = val

    def _to_int(s: str) -> int:
        try:
            return int(s)
        except Exception:
            return 0

    return {
        "source": meta_raw.get("Source", "unknown"),
        "subreddits": [s.strip() for s in meta_raw.get("Subreddits", "").split(",") if s.strip()],
        "post_count": _to_int(meta_raw.get("PostCount", "0")),
        "comment_count": _to_int(meta_raw.get("CommentCount", "0")),
        "generated_at_utc": meta_raw.get("GeneratedAt(UTC)"),
        "window": meta_raw.get("Window"),
    }


def invoke_social_agent(asset: str, *, config: Optional[RunnableConfig] = None) -> SocialReport:
    """Invoke the Social Agent and return a structured dict for CIO consumption.

    This function is the intended integration point for the CIO Agent. It does
    not print and does not interact with end users. It simply returns the
    structured result.

    Args:
        asset: Asset ticker such as ``\"BTC\"`` or ``\"NVDA\"``.
        config: Optional LangChain runnable config.

    Returns:
        A ``SocialReport`` dict containing at least:
        - ``sentiment`` / ``keywords`` / ``summary`` / ``report_path``
        plus an ``asset`` echo field when available.
    """

    asset_norm = (asset or "").strip().upper()

    # Deterministic pipeline (preferred for stability):
    # Avoid relying on the ReAct graph's final text formatting; still uses LLM for NLP.
    from app.social import export_tools, nlp_tools
    from app.social.reddit import tools as reddit_tools

    corpus = reddit_tools.get_reddit_discussion.invoke({"asset": asset_norm})
    meta = _extract_ingest_meta_from_text(corpus)
    nlp_result = nlp_tools.analyze_reddit_text.invoke({"asset": asset_norm, "text": corpus})
    report_obj = export_tools.build_social_report.invoke(
        {"asset": asset_norm, "nlp_result": dict(nlp_result), "meta": meta}
    )
    report_path = export_tools.save_social_report.invoke(
        {"asset": asset_norm, "report": cast(Dict[str, Any], report_obj)}
    )
    report_obj["report_path"] = report_path
    return cast(SocialReport, report_obj)

