"""Type contracts for the daily digest configuration and payload blocks."""

from __future__ import annotations

from typing import Literal, TypedDict


class DailyDigestConfig(TypedDict):
    """Runtime configuration for scheduled daily digest generation."""

    enabled: bool
    time: str
    timezone: str
    tickers: list[str]
    macro_query: str
    recipients: list[str]
    sender: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_starttls: bool
    smtp_use_ssl: bool


class TechnicalSection(TypedDict, total=False):
    ticker: str
    asset_type: Literal["equity", "crypto"]
    status: Literal["ok", "error"]
    summary: str
    trend: str
    daily_change_pct: float | None
    levels: dict[str, float | None]
    indicators: dict[str, float | None]
    ml_signal: dict[str, object] | None
    error: str | None


class MacroNewsSection(TypedDict, total=False):
    status: Literal["ok", "error"]
    query: str
    window_start: str
    window_end: str
    summary_points: list[str]
    sources: list[dict[str, object]]
    error: str | None


class CioSummarySection(TypedDict, total=False):
    status: Literal["ok", "error"]
    text: str
    error: str | None


class EmailDelivery(TypedDict, total=False):
    status: Literal["sent", "skipped", "error"]
    subject: str
    recipients: list[str]
    error: str | None


class EmailContent(TypedDict):
    subject: str
    text_body: str
    html_body: str


class DailyDigestPayload(TypedDict, total=False):
    module: str
    run_id: str
    meta: dict[str, object]
    tickers: list[str]
    technical_sections: list[TechnicalSection]
    macro_news: MacroNewsSection
    cio_summary: CioSummarySection
    email: EmailDelivery
