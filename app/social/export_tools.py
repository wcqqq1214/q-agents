"""Export tools for Social Agent outputs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from langchain_core.tools import tool


def _now_compact_utc8() -> str:
    """Return YYYYMMDD_HHMMSS timestamp in UTC+8."""

    tz = timezone(timedelta(hours=8))
    return datetime.now(timezone.utc).astimezone(tz).replace(microsecond=0).strftime("%Y%m%d_%H%M%S")


@tool("save_social_report")
def save_social_report(asset: str, report: Dict[str, Any]) -> str:
    """Persist Social Agent report as a JSON file under ./data/reports/ and return its path.

    The CIO agent consumes social sentiment as structured data. To support
    auditability and later offline analysis, this tool stores the report on
    disk and returns the generated file path.

    Output file naming convention:
        ``./data/reports/{asset_lower}_reddit_sentiment_{YYYYMMDD_HHMMSS}.json``

    Args:
        asset: Asset identifier such as ``\"BTC\"`` or ``\"NVDA\"``.
        report: JSON-serializable dictionary containing the structured social
            sentiment fields, usually ``sentiment``, ``keywords``, and
            ``summary`` plus optional metadata.

    Returns:
        String path to the saved JSON report file.

    Raises:
        ValueError: If asset is empty or report is not a dict.
        OSError: If the filesystem cannot be written.
    """

    asset_norm = (asset or "").strip().lower()
    if not asset_norm:
        raise ValueError("asset is empty.")
    if not isinstance(report, dict):
        raise ValueError("report must be a dict.")

    reports_dir = Path("data/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    ts = _now_compact_utc8()
    path = reports_dir / f"{asset_norm}_reddit_sentiment_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


@tool("build_social_report")
def build_social_report(asset: str, nlp_result: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """Build the final Social Agent report object in a deterministic way.

    This tool exists to reduce output instability caused by LLM formatting.
    Instead of asking the model to manually merge meta fields into the final
    JSON, we let the tool assemble the final object that will be saved.

    Args:
        asset: Asset identifier such as ``\"BTC\"`` or ``\"NVDA\"``.
        nlp_result: The structured NLP output dict, expected to contain:
            - ``sentiment`` (label)
            - ``keywords`` (list of strings)
            - ``summary`` (string)
        meta: Ingestion meta information, typically including:
            - ``source`` (\"json\" or \"playwright\")
            - ``post_count`` / ``comment_count``
            - ``subreddits`` and optional ``post_urls`` / ``errors``

    Returns:
        A merged dict that always includes ``asset``, the NLP fields, and ``meta``.
    """

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")
    if not isinstance(nlp_result, dict):
        raise ValueError("nlp_result must be a dict.")
    if not isinstance(meta, dict):
        raise ValueError("meta must be a dict.")

    out: Dict[str, Any] = {"asset": asset_norm, "meta": meta}
    out.update(nlp_result)
    return out

