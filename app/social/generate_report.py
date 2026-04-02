"""Social module unified report generator.

This module exposes a stable entry point:
    generate_report(asset: str, run_dir: str) -> dict
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, TypedDict, cast

from app.reporting.writer import write_json
from app.social.entrypoint import _extract_ingest_meta_from_text
from app.social.export_tools import build_social_report
from app.social.nlp_tools import analyze_reddit_text
from app.social.reddit.tools import get_reddit_discussion


class SocialBundle(TypedDict, total=False):
    asset: str
    module: str
    meta: Dict[str, Any]
    sentiment: str
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
    keywords = report.get("keywords", []) if isinstance(report.get("keywords"), list) else []
    meta = report.get("meta", {}) if isinstance(report.get("meta"), dict) else {}
    subreddits = meta.get("subreddits", []) if isinstance(meta.get("subreddits"), list) else []

    lines = [
        "# Social Retail Sentiment Report",
        "",
        "## Sentiment Snapshot",
        f"- **Asset**: `{asset}`",
        f"- **Sentiment**: `{sentiment}`",
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

    return "\n".join(lines)


def generate_report(asset: str, run_dir: str) -> SocialBundle:
    """Generate the Social report and persist it as `social.json` inside run_dir."""

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus = cast(str, get_reddit_discussion.invoke({"asset": asset_norm}))
    ingest_meta = _extract_ingest_meta_from_text(corpus)
    ingest_meta["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    nlp_result = cast(
        Dict[str, Any],
        analyze_reddit_text.invoke({"asset": asset_norm, "text": corpus}),
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
    return cast(SocialBundle, report_obj)
