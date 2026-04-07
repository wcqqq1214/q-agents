"""Social module unified report generator.

This module exposes a stable entry point:
    generate_report(asset: str, run_dir: str) -> dict
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, TypedDict, cast

from app.analysis import AnalysisRuntime
from app.reporting.writer import write_json
from app.social.export_tools import build_social_report
from app.social.ingest_meta import extract_ingest_meta_from_text
from app.social.nlp_tools import analyze_reddit_text
from app.social.reddit.tools import get_reddit_discussion


class SocialBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    sentiment: str
    signal_available: bool
    coverage_status: str
    keywords: list[str]
    summary: str
    markdown_report: str
    report_path: str


def _format_markdown_value(value: Any) -> str:
    """Render a compact value for markdown reports."""

    if value is None or value == "":
        return "N/A"
    return str(value)


def _build_social_markdown(report: Dict[str, Any]) -> str:
    """Build a deterministic markdown view from the structured social report."""

    asset = str(report.get("asset", "UNKNOWN")).upper()
    sentiment = _format_markdown_value(report.get("sentiment"))
    summary = str(report.get("summary") or "No social summary available.")
    signal_available = bool(
        report.get("signal_available", report.get("sentiment") != "unavailable")
    )
    coverage_status = str(
        report.get("coverage_status") or ("available" if signal_available else "unavailable")
    )
    keywords = report.get("keywords", []) if isinstance(report.get("keywords"), list) else []
    meta = report.get("meta", {}) if isinstance(report.get("meta"), dict) else {}
    subreddits = meta.get("subreddits", []) if isinstance(meta.get("subreddits"), list) else []

    lines = [
        "# Social Retail Sentiment Report",
        "",
        "## Sentiment Snapshot",
        f"- **Asset**: `{asset}`",
        f"- **Sentiment**: `{sentiment}`",
        f"- **Signal available**: `{'yes' if signal_available else 'no'}`",
        f"- **Coverage status**: `{coverage_status}`",
        f"- **Summary**: {summary}",
        "",
        "## Keywords",
    ]

    if keywords:
        lines.extend(
            f"- `{keyword}`" for keyword in keywords[:5] if isinstance(keyword, str) and keyword
        )
    else:
        lines.append("- No dominant keywords were extracted.")

    lines.extend(
        [
            "",
            "## Coverage",
            f"- **Source**: `{_format_markdown_value(meta.get('source'))}`",
            f"- **Window**: `{_format_markdown_value(meta.get('window'))}`",
            f"- **Posts analyzed**: `{_format_markdown_value(meta.get('post_count'))}`",
            f"- **Comments analyzed**: `{_format_markdown_value(meta.get('comment_count'))}`",
            (
                "- **Subreddits**: "
                + (", ".join(f"`{item}`" for item in subreddits) if subreddits else "N/A")
            ),
        ]
    )

    if not signal_available:
        lines.extend(
            [
                "",
                "## Interpretation Rule",
                "- Exclude this report from retail sentiment judgment because Reddit coverage was unavailable or unreliable for this run.",
            ]
        )

    return "\n".join(lines)


def _coerce_social_signal(
    nlp_result: Dict[str, Any],
    ingest_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize no-signal Reddit coverage into an explicit unavailable payload."""

    post_count = ingest_meta.get("post_count") or 0
    comment_count = ingest_meta.get("comment_count") or 0
    zero_coverage = post_count == 0 and comment_count == 0
    explicit_unavailable = (
        nlp_result.get("signal_available") is False
        or nlp_result.get("coverage_status") == "unavailable"
        or nlp_result.get("sentiment") == "unavailable"
    )

    if zero_coverage or explicit_unavailable:
        return {
            **dict(nlp_result),
            "sentiment": "unavailable",
            "keywords": [],
            "summary": (
                "Reddit social signal unavailable; excluded from retail sentiment judgment because no usable discussion data was captured in the last 24 hours."
            ),
            "signal_available": False,
            "coverage_status": "unavailable",
        }

    out = dict(nlp_result)
    out.setdefault("signal_available", True)
    out.setdefault("coverage_status", "available")
    return out


def generate_report(
    asset: str,
    run_dir: str,
    runtime: AnalysisRuntime | None = None,
) -> SocialBundle:
    """Generate the Social report and persist it as `social.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if runtime is not None:
        runtime.emit_stage("social", "running", "Fetching Reddit discussion")
        runtime.emit_tool_call(
            "social",
            "get_reddit_discussion",
            "Fetching Reddit discussion",
            {"asset": asset_norm},
        )
    corpus = cast(str, get_reddit_discussion.invoke({"asset": asset_norm}))
    ingest_meta = extract_ingest_meta_from_text(corpus)
    ingest_meta["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if runtime is not None:
        runtime.emit_tool_result(
            "social",
            "get_reddit_discussion",
            (
                f"Fetched {ingest_meta.get('post_count', 0)} Reddit posts and "
                f"{ingest_meta.get('comment_count', 0)} comments"
            ),
            {
                "post_count": ingest_meta.get("post_count", 0),
                "comment_count": ingest_meta.get("comment_count", 0),
                "source": ingest_meta.get("source"),
            },
        )

    if runtime is not None:
        runtime.emit_tool_call(
            "social",
            "analyze_reddit_text",
            "Running social sentiment analysis",
            {"asset": asset_norm},
        )
    nlp_result = cast(
        Dict[str, Any],
        analyze_reddit_text.invoke({"asset": asset_norm, "text": corpus}),
    )
    nlp_result = _coerce_social_signal(nlp_result, ingest_meta)
    if runtime is not None:
        runtime.emit_tool_result(
            "social",
            "analyze_reddit_text",
            "Social sentiment analysis completed",
            {
                "sentiment": nlp_result.get("sentiment"),
                "signal_available": nlp_result.get("signal_available"),
            },
        )
    report_obj = cast(
        Dict[str, Any],
        build_social_report.invoke(
            {"asset": asset_norm, "nlp_result": dict(nlp_result), "meta": ingest_meta}
        ),
    )
    report_obj["module"] = "social"
    report_obj["markdown_report"] = _build_social_markdown(report_obj)

    path = out_dir / "social.json"
    write_json(path, report_obj)
    report_obj["report_path"] = str(path)
    if runtime is not None:
        runtime.emit_stage(
            "social",
            "completed",
            "Social report completed",
            {"artifact": "social", "report_path": str(path)},
        )
    return cast(SocialBundle, report_obj)
