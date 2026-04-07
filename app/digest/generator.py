"""Daily digest orchestration, rendering, persistence, and delivery."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.digest.cio import build_cio_summary
from app.digest.macro_news import build_macro_news_section
from app.digest.models import (
    DailyDigestConfig,
    DailyDigestPayload,
    MacroNewsSection,
    TechnicalSection,
)
from app.digest.render import render_digest_email
from app.digest.technical import build_technical_section, classify_asset_type
from app.reporting.writer import write_json
from app.services.email_service import send_digest_email

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TECHNICAL_SECTIONS = 3


def _digest_now(config: DailyDigestConfig, now: datetime | None = None) -> datetime:
    tz = ZoneInfo(config["timezone"])
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _digest_run_id(now_local: datetime) -> str:
    return f"{now_local.date().isoformat()}_daily_digest"


def _default_base_dir() -> Path:
    return Path("data") / "reports" / "digests"


def _build_meta(config: DailyDigestConfig, now_local: datetime) -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "timezone": config["timezone"],
        "scheduled_time": config["time"],
        "digest_date": now_local.date().isoformat(),
    }


def _make_run_dir(
    config: DailyDigestConfig,
    base_dir: Path | None,
    now_local: datetime,
) -> tuple[str, Path]:
    resolved_base_dir = base_dir or _default_base_dir()
    run_id = _digest_run_id(now_local)
    run_dir = resolved_base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return (run_id, run_dir)


def _macro_news_error_section(
    config: DailyDigestConfig, now_local: datetime, exc: Exception
) -> MacroNewsSection:
    window_end = now_local
    window_start = window_end - timedelta(days=1)
    return {
        "status": "error",
        "query": config["macro_query"],
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "summary_points": [],
        "sources": [],
        "error": f"{type(exc).__name__}: {exc}",
    }


def _technical_error_section(ticker: str, exc: Exception) -> TechnicalSection:
    asset_type = classify_asset_type(ticker)
    return {
        "ticker": ticker,
        "asset_type": "crypto" if asset_type == "crypto" else "equity",
        "status": "error",
        "summary": "Technical snapshot unavailable for this run.",
        "trend": "neutral",
        "levels": {"support": None, "resistance": None},
        "indicators": {
            "last_close": None,
            "sma_20": None,
            "macd_line": None,
            "macd_signal": None,
            "macd_histogram": None,
            "price_change_pct": None,
        },
        "ml_signal": None,
        "error": f"{type(exc).__name__}: {exc}",
    }


def _persist_digest_artifacts(
    run_dir: Path,
    payload: DailyDigestPayload,
    text_body: str,
    html_body: str,
) -> None:
    (run_dir / "email.txt").write_text(text_body, encoding="utf-8")
    (run_dir / "email.html").write_text(html_body, encoding="utf-8")
    write_json(run_dir / "digest.json", payload)


async def generate_daily_digest(
    config: DailyDigestConfig,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> DailyDigestPayload:
    """Generate, persist, and deliver one daily digest run.

    Args:
        config: Normalized digest runtime configuration.
        base_dir: Optional override for the digest artifact root.
        now: Optional clock override for deterministic testing.

    Returns:
        DailyDigestPayload: Persisted digest payload including delivery metadata.
    """

    now_local = _digest_now(config, now)
    run_id, run_dir = _make_run_dir(config, base_dir, now_local)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TECHNICAL_SECTIONS)

    async def _bounded_build(ticker: str) -> TechnicalSection:
        async with semaphore:
            try:
                return await build_technical_section(ticker, run_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Daily digest technical section failed for %s: %s", ticker, exc)
                return _technical_error_section(ticker, exc)

    technical_sections = list(
        await asyncio.gather(*[_bounded_build(ticker) for ticker in config["tickers"]])
    )

    try:
        macro_news = await asyncio.to_thread(build_macro_news_section, config, now_local)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Daily digest macro news section failed: %s", exc)
        macro_news = _macro_news_error_section(config, now_local, exc)

    try:
        cio_summary = await asyncio.to_thread(build_cio_summary, technical_sections, macro_news)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Daily digest CIO summary failed: %s", exc)
        cio_summary = {"status": "error", "text": "", "error": f"{type(exc).__name__}: {exc}"}

    payload: DailyDigestPayload = {
        "module": "daily_digest",
        "run_id": run_id,
        "meta": _build_meta(config, now_local),
        "tickers": list(config["tickers"]),
        "technical_sections": technical_sections,
        "macro_news": macro_news,
        "cio_summary": cio_summary,
        "email": {
            "status": "skipped",
            "subject": "",
            "recipients": list(config["recipients"]),
            "error": None,
        },
    }
    email_content = render_digest_email(payload)
    payload["email"] = send_digest_email(
        email_content["subject"],
        email_content["text_body"],
        email_content["html_body"],
        config,
    )
    _persist_digest_artifacts(
        run_dir,
        payload,
        email_content["text_body"],
        email_content["html_body"],
    )
    return payload
