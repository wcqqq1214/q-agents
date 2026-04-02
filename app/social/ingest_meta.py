"""Utilities for parsing social-ingestion metadata."""

from __future__ import annotations

from typing import Dict


def extract_ingest_meta_from_text(text: str) -> Dict[str, object]:
    """Extract ingestion metadata from get_reddit_discussion header lines."""

    meta_raw: Dict[str, str] = {}
    for line in (text or "").splitlines()[:20]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        field = key.strip()
        if field in {
            "Asset",
            "Window",
            "Subreddits",
            "Source",
            "PostCount",
            "CommentCount",
            "GeneratedAt(UTC)",
        }:
            meta_raw[field] = value.strip()

    def _to_int(raw: str) -> int:
        try:
            return int(raw)
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
