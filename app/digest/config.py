"""Configuration helpers for daily digest scheduling and delivery."""

from __future__ import annotations

import logging
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from app.digest.models import DailyDigestConfig

logger = logging.getLogger(__name__)

DEFAULT_MACRO_QUERY = "US stock market macro economy Fed earnings bitcoin ethereum"
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BTC", "ETH"]

_TIME_RE = re.compile(r"^(?P<hour>\d{2}):(?P<minute>\d{2})$")


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean-like environment value."""

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_tickers(raw: str | None) -> list[str]:
    """Normalize comma-separated ticker symbols."""

    if not raw:
        return []
    parts = [chunk.strip().upper() for chunk in raw.split(",")]
    return [ticker for ticker in parts if ticker]


def _is_valid_email(value: str) -> bool:
    """Return whether the value matches a lightweight email shape."""

    candidate = value.strip()
    if not candidate or " " in candidate:
        return False
    if candidate.count("@") != 1:
        return False
    local, _, domain = candidate.partition("@")
    if "@" in domain:
        return False
    return bool(local and "." in domain and not domain.startswith(".") and not domain.endswith("."))


def _filter_recipients_with_count(raw: str | None) -> tuple[list[str], int]:
    """Filter invalid recipients and return dropped count."""

    if not raw:
        return ([], 0)
    candidates = [item.strip() for item in raw.split(",") if item.strip()]
    valid: list[str] = []
    dropped = 0
    for candidate in candidates:
        if _is_valid_email(candidate):
            valid.append(candidate)
        else:
            dropped += 1
    return (valid, dropped)


def _resolve_sender() -> str | None:
    """Resolve sender from digest-specific env var or SMTP username fallback."""

    explicit = (os.getenv("DAILY_DIGEST_FROM") or "").strip()
    if explicit:
        return explicit
    fallback = (os.getenv("SMTP_USERNAME") or "").strip()
    return fallback or None


def _parse_hh_mm(raw: str) -> tuple[int, int]:
    """Parse HH:MM and validate ranges."""

    match = _TIME_RE.match((raw or "").strip())
    if match is None:
        raise ValueError(f"Invalid HH:MM value: {raw!r}")
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid time value: {raw!r}")
    return (hour, minute)


def load_daily_digest_config() -> DailyDigestConfig:
    """Load and normalize daily digest config from environment variables."""

    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_raw)
        if smtp_port <= 0 or smtp_port > 65535:
            raise ValueError(f"SMTP_PORT out of range: {smtp_port}")
    except (TypeError, ValueError):
        logger.warning("Invalid SMTP_PORT=%r; falling back to 587", smtp_port_raw)
        smtp_port = 587

    tickers = _normalize_tickers(os.getenv("DAILY_DIGEST_TICKERS"))
    if not tickers:
        logger.warning(
            "Daily digest ticker list is empty after normalization; falling back to default tickers"
        )
        tickers = list(DEFAULT_TICKERS)

    recipients, dropped_recipient_count = _filter_recipients_with_count(
        os.getenv("DAILY_DIGEST_RECIPIENTS", "")
    )
    if dropped_recipient_count:
        logger.warning("Daily digest dropped %d invalid recipient(s)", dropped_recipient_count)

    return {
        "enabled": _parse_bool(os.getenv("DAILY_DIGEST_ENABLED"), default=False),
        "time": os.getenv("DAILY_DIGEST_TIME", "08:00"),
        "timezone": os.getenv("DAILY_DIGEST_TIMEZONE", "Asia/Shanghai"),
        "tickers": tickers,
        "macro_query": os.getenv("DAILY_DIGEST_MACRO_QUERY", DEFAULT_MACRO_QUERY),
        "recipients": recipients,
        "sender": _resolve_sender(),
        "smtp_host": os.getenv("SMTP_HOST"),
        "smtp_port": smtp_port,
        "smtp_username": os.getenv("SMTP_USERNAME"),
        "smtp_password": os.getenv("SMTP_PASSWORD"),
        "smtp_use_starttls": _parse_bool(os.getenv("SMTP_USE_STARTTLS"), default=True),
        "smtp_use_ssl": _parse_bool(os.getenv("SMTP_USE_SSL"), default=False),
    }


def build_daily_digest_trigger(config: DailyDigestConfig) -> CronTrigger | None:
    """Build the cron trigger for the digest job, or return ``None`` when invalid."""

    try:
        hour, minute = _parse_hh_mm(config["time"])
        timezone = ZoneInfo(config["timezone"])
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return CronTrigger(hour=hour, minute=minute, timezone=timezone)
