"""Render structured daily digest payloads into email-ready content."""

from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import urlparse

from app.digest.models import DailyDigestPayload, EmailContent

_POSITIVE_CHANGE_COLOR = "#0a7f2e"
_NEGATIVE_CHANGE_COLOR = "#b91c1c"
_NEUTRAL_CHANGE_COLOR = "#6b7280"
_MISSING_SUMMARY = (
    "Summary unavailable from the upstream news feed. "
    "This remains a macro watchpoint worth checking in the original article."
)
_ONE_SENTENCE_APPEND = "This remains a macro watchpoint for today's cross-asset risk sentiment."
_LINK_UNAVAILABLE = "Link unavailable"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_LEADING_MARKUP_RE = re.compile(r"^(?:[#*\-]+\s*)+")
_INITIALISM_RE = re.compile(r"\b(?:[A-Z]\.){2,}")


def _format_price(value: Any) -> str:
    number = value if isinstance(value, (int, float)) else None
    return "--" if number is None else f"{float(number):.2f}"


def _format_change_value(change_pct: Any) -> tuple[str, str]:
    if not isinstance(change_pct, (int, float)):
        return ("--", _NEUTRAL_CHANGE_COLOR)

    rounded = round(float(change_pct), 2)
    if rounded > 0:
        return (f"+{rounded:.2f}%", _POSITIVE_CHANGE_COLOR)
    if rounded < 0:
        return (f"{rounded:.2f}%", _NEGATIVE_CHANGE_COLOR)
    return ("0.00%", _NEUTRAL_CHANGE_COLOR)


def _normalize_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped[-1] not in ".!?":
        return f"{stripped}."
    return stripped


def _clean_macro_text(text: str) -> str:
    compact = " ".join(text.split()).strip()
    compact = _LEADING_MARKUP_RE.sub("", compact)
    return compact.strip()


def _macro_dedupe_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_title_duplicate(sentence_key: str, title_key: str) -> bool:
    return bool(title_key) and (
        sentence_key == title_key
        or title_key.startswith(f"{sentence_key} ")
        or sentence_key.startswith(f"{title_key} ")
    )


def _protect_initialisms(text: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = f"__INITIALISM_{len(replacements)}__"
        replacements[token] = match.group(0)
        return token

    return (_INITIALISM_RE.sub(_replace, text), replacements)


def _restore_initialisms(text: str, replacements: dict[str, str]) -> str:
    restored = text
    for token, original in replacements.items():
        restored = restored.replace(token, original)
    return restored


def _build_macro_summary(article: dict[str, Any]) -> str:
    snippet = article.get("snippet")
    if not isinstance(snippet, str) or not snippet.strip():
        return _MISSING_SUMMARY

    title = article.get("title")
    title_key = _macro_dedupe_key(_clean_macro_text(title)) if isinstance(title, str) else ""
    protected_snippet, replacements = _protect_initialisms(snippet.strip())

    sentences: list[str] = []
    seen: set[str] = set()
    for part in _SENTENCE_SPLIT_RE.split(protected_snippet):
        cleaned = _clean_macro_text(_restore_initialisms(part, replacements))
        normalized = _normalize_sentence(cleaned)
        if not normalized:
            continue
        dedupe_key = _macro_dedupe_key(cleaned)
        if not dedupe_key or dedupe_key in seen or _is_title_duplicate(dedupe_key, title_key):
            continue
        seen.add(dedupe_key)
        sentences.append(normalized)

    if len(sentences) >= 2:
        return " ".join(sentences[:2])
    if len(sentences) == 1:
        return f"{sentences[0]} {_ONE_SENTENCE_APPEND}"
    return _MISSING_SUMMARY


def _macro_link(article: dict[str, Any]) -> str:
    url = article.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return _LINK_UNAVAILABLE


def _macro_source(article: dict[str, Any]) -> str:
    source = article.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip()

    title = article.get("title")
    if isinstance(title, str) and " - " in title:
        fallback = title.rsplit(" - ", 1)[-1].strip()
        if fallback:
            return fallback

    link = _macro_link(article)
    if link == _LINK_UNAVAILABLE:
        return "Unknown source"

    hostname = urlparse(link).netloc.strip().lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "Unknown source"


def _render_text(payload: DailyDigestPayload) -> str:
    meta = payload["meta"]
    subject = f"Daily Market Digest | {meta['digest_date']}"
    lines = [
        subject,
        f"Schedule: {meta['scheduled_time']} {meta['timezone']}",
        "",
        "Technical Overview",
    ]

    technical_sections = payload.get("technical_sections", [])
    if technical_sections:
        for section in technical_sections:
            last_close = None
            indicators = section.get("indicators", {})
            if isinstance(indicators, dict):
                last_close = indicators.get("last_close")
            change_text, _ = _format_change_value(section.get("daily_change_pct"))
            lines.append(
                f"{section.get('ticker', 'UNKNOWN')} {_format_price(last_close)} ({change_text})"
            )
    else:
        lines.append("No technical sections available.")

    lines.extend(["", "Macro News"])
    macro_news = payload.get("macro_news", {})
    raw_sources = macro_news.get("sources", [])
    sources = [item for item in raw_sources if isinstance(item, dict)][:3]
    if macro_news.get("status") == "ok" and sources:
        for index, article in enumerate(sources, start=1):
            lines.extend(
                [
                    f"{index}. {article.get('title') or 'Untitled macro item'}",
                    f"Summary: {_build_macro_summary(article)}",
                    f"Source: {_macro_source(article)}",
                    f"Link: {_macro_link(article)}",
                    "",
                ]
            )
        lines.pop()
    else:
        lines.append(f"Unavailable: {macro_news.get('error') or 'macro news unavailable'}")

    lines.extend(["", "CIO Summary"])
    cio_summary = payload.get("cio_summary", {})
    if cio_summary.get("status") == "ok" and cio_summary.get("text"):
        lines.append(str(cio_summary["text"]))
    else:
        lines.append(f"Unavailable: {cio_summary.get('error') or 'cio summary unavailable'}")

    return "\n".join(lines)


def _render_html(payload: DailyDigestPayload) -> str:
    meta = payload["meta"]
    subject = f"Daily Market Digest | {meta['digest_date']}"

    technical_sections = payload.get("technical_sections", [])
    if technical_sections:
        technical_items = []
        for section in technical_sections:
            indicators = section.get("indicators", {})
            last_close = indicators.get("last_close") if isinstance(indicators, dict) else None
            change_text, change_color = _format_change_value(section.get("daily_change_pct"))
            technical_items.append(
                "<li>"
                f"<b>{escape(str(section.get('ticker', 'UNKNOWN')))}</b> "
                f"{escape(_format_price(last_close))} "
                f'(<span style="color: {change_color};">{escape(change_text)}</span>)'
                "</li>"
            )
        technical_html = "".join(technical_items)
    else:
        technical_html = "<li>No technical sections available.</li>"

    macro_news = payload.get("macro_news", {})
    raw_sources = macro_news.get("sources", [])
    sources = [item for item in raw_sources if isinstance(item, dict)][:3]
    if macro_news.get("status") == "ok" and sources:
        macro_items = []
        for article in sources:
            link = _macro_link(article)
            if link == _LINK_UNAVAILABLE:
                link_html = escape(link)
            else:
                safe_link = escape(link, quote=True)
                link_html = f'<a href="{safe_link}">{escape(link)}</a>'
            macro_items.append(
                "<li>"
                f"<b>{escape(str(article.get('title') or 'Untitled macro item'))}</b><br>"
                f"Summary: {escape(_build_macro_summary(article))}<br>"
                f"Source: {escape(_macro_source(article))}<br>"
                f"Link: {link_html}"
                "</li>"
            )
        macro_html = "".join(macro_items)
    else:
        macro_html = (
            "<li>"
            f"Unavailable: {escape(str(macro_news.get('error') or 'macro news unavailable'))}"
            "</li>"
        )

    cio_summary = payload.get("cio_summary", {})
    if cio_summary.get("status") == "ok" and cio_summary.get("text"):
        cio_html = escape(str(cio_summary["text"]))
    else:
        cio_html = (
            f"Unavailable: {escape(str(cio_summary.get('error') or 'cio summary unavailable'))}"
        )

    return (
        "<html><body>"
        f"<h1>{escape(subject)}</h1>"
        f"<p>Schedule: {escape(str(meta['scheduled_time']))} {escape(str(meta['timezone']))}</p>"
        "<h2>Technical Overview</h2>"
        f"<ul>{technical_html}</ul>"
        "<h2>Macro News</h2>"
        f"<ol>{macro_html}</ol>"
        "<h2>CIO Summary</h2>"
        f"<p>{cio_html}</p>"
        "</body></html>"
    )


def render_digest_email(payload: DailyDigestPayload) -> EmailContent:
    """Render digest payload into text and HTML email bodies.

    Args:
        payload: Persisted digest payload containing run metadata and sections.

    Returns:
        EmailContent: Subject plus text and HTML bodies for multipart delivery.
    """

    digest_date = str(payload["meta"]["digest_date"])
    subject = f"Daily Market Digest | {digest_date}"
    return {
        "subject": subject,
        "text_body": _render_text(payload),
        "html_body": _render_html(payload),
    }
