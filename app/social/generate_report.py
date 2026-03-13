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
    report_path: str


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

    nlp_result = cast(Dict[str, Any], analyze_reddit_text.invoke({"asset": asset_norm, "text": corpus}))
    report_obj = cast(
        Dict[str, Any],
        build_social_report.invoke({"asset": asset_norm, "nlp_result": dict(nlp_result), "meta": ingest_meta}),
    )
    report_obj["module"] = "social"

    path = out_dir / "social.json"
    write_json(path, report_obj)
    report_obj["report_path"] = str(path)
    return cast(SocialBundle, report_obj)

