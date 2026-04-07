"""Macro-news aggregation for the daily digest pipeline."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.digest.models import DailyDigestConfig, MacroNewsSection
from app.tools.local_tools import search_realtime_news

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_published_time(raw: object) -> datetime | None:
    text = _normalize_text(raw)
    if not text:
        return None

    lower = text.lower()
    now_utc = datetime.now(timezone.utc)
    if lower == "yesterday":
        return now_utc - timedelta(days=1)
    if lower.endswith(" ago"):
        parts = lower.split()
        try:
            if len(parts) >= 3:
                value = int(parts[0])
                unit = parts[1]
                if unit.startswith("hour"):
                    return now_utc - timedelta(hours=value)
                if unit.startswith("day"):
                    return now_utc - timedelta(days=value)
                if unit.startswith("week"):
                    return now_utc - timedelta(weeks=value)
        except (TypeError, ValueError):
            return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        parsed_iso = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed_iso.tzinfo is None:
        parsed_iso = parsed_iso.replace(tzinfo=timezone.utc)
    return parsed_iso


def _digest_window(now: datetime | None, timezone_name: str) -> tuple[datetime, datetime]:
    timezone_info = ZoneInfo(timezone_name)
    if now is None:
        window_end = datetime.now(timezone_info)
    elif now.tzinfo is None:
        window_end = now.replace(tzinfo=timezone_info)
    else:
        window_end = now.astimezone(timezone_info)
    return (window_end - timedelta(days=1), window_end)


def _normalize_articles(raw: object) -> list[dict[str, object]]:
    if isinstance(raw, str):
        payload = json.loads(raw)
    elif isinstance(raw, dict):
        payload = raw
    else:
        return []

    articles_raw = payload.get("articles", [])
    if not isinstance(articles_raw, list):
        return []

    articles: list[dict[str, object]] = []
    for item in articles_raw:
        if not isinstance(item, dict):
            continue
        articles.append(
            {
                "title": _normalize_text(item.get("title")),
                "url": _normalize_text(item.get("url")),
                "source": _normalize_text(item.get("source")),
                "published_time": item.get("published_time"),
                "snippet": _normalize_text(item.get("snippet")),
            }
        )
    return articles


def _is_within_window(
    article: dict[str, object], window_start: datetime, window_end: datetime
) -> bool:
    published_dt = _parse_published_time(article.get("published_time"))
    if published_dt is None:
        return False
    published_in_tz = published_dt.astimezone(window_end.tzinfo or timezone.utc)
    return window_start <= published_in_tz <= window_end


def _dedupe_articles(articles: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for article in articles:
        url = _normalize_text(article.get("url"))
        title = _normalize_text(article.get("title")).lower()
        key = url.lower() if url else title
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


def _backfill_missing_timestamp_articles(
    filtered: list[dict[str, object]],
    all_articles: list[dict[str, object]],
    minimum_count: int,
) -> list[dict[str, object]]:
    combined = list(filtered)
    existing = {
        (
            _normalize_text(article.get("url")).lower()
            or _normalize_text(article.get("title")).lower()
        )
        for article in combined
    }
    if len(combined) >= minimum_count:
        return combined

    for article in all_articles:
        if _parse_published_time(article.get("published_time")) is not None:
            continue
        key = (
            _normalize_text(article.get("url")).lower()
            or _normalize_text(article.get("title")).lower()
        )
        if not key or key in existing:
            continue
        combined.append(article)
        existing.add(key)
        if len(combined) >= minimum_count:
            break
    return combined


def _summarize_to_bullets(
    articles: list[dict[str, object]],
    minimum_points: int = 3,
    maximum_points: int = 5,
) -> list[str]:
    points: list[str] = []
    for article in articles[:maximum_points]:
        headline = _normalize_text(article.get("title"))
        snippet = _normalize_text(article.get("snippet"))
        source = _normalize_text(article.get("source"))
        if headline and source:
            points.append(f"{headline} ({source})")
        elif headline:
            points.append(headline)
        elif snippet:
            points.append(snippet)

    if len(points) >= minimum_points:
        return points[:maximum_points]
    return points


def build_macro_news_section(
    config: DailyDigestConfig,
    now: datetime | None = None,
) -> MacroNewsSection:
    """Build the digest-level macro news section from one search query.

    Args:
        config: Normalized digest configuration containing macro query and timezone.
        now: Optional clock override for deterministic testing.

    Returns:
        MacroNewsSection: Summary bullets and source metadata, or an error
        section when news retrieval or normalization fails.
    """

    window_start, window_end = _digest_window(now, config["timezone"])
    base_section: MacroNewsSection = {
        "query": config["macro_query"],
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "summary_points": [],
        "sources": [],
    }

    try:
        raw = search_realtime_news.invoke({"query": config["macro_query"], "limit": 8})
        articles = _normalize_articles(raw)
        if not articles:
            raise ValueError("No macro news articles returned")

        filtered = _dedupe_articles(
            [
                article
                for article in articles
                if _is_within_window(article, window_start, window_end)
            ]
        )
        tolerant = _backfill_missing_timestamp_articles(filtered, articles, minimum_count=3)
        deduped = _dedupe_articles(tolerant)[:8]
        summary_points = _summarize_to_bullets(deduped, minimum_points=3, maximum_points=5)
        if not summary_points:
            raise ValueError("No macro news articles available after filtering")

        return {
            **base_section,
            "status": "ok",
            "summary_points": summary_points,
            "sources": deduped,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build macro news section: %s", exc)
        return {
            **base_section,
            "status": "error",
            "summary_points": [],
            "sources": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
