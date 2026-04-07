"""Tests for daily digest orchestration and persistence."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.digest.generator import generate_daily_digest
from app.digest.macro_news import build_macro_news_section


@pytest.fixture
def config() -> dict[str, object]:
    """Return a representative digest configuration for tests."""

    return {
        "enabled": True,
        "time": "08:00",
        "timezone": "Asia/Shanghai",
        "tickers": ["AAPL", "MSFT", "BTC"],
        "macro_query": "US stock market macro economy Fed earnings bitcoin ethereum",
        "recipients": ["alice@example.com"],
        "sender": "digest@example.com",
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "smtp_use_starttls": True,
        "smtp_use_ssl": False,
    }


async def fake_out_of_order_section_builder(ticker: str, run_dir) -> dict[str, object]:
    """Return technical sections after ticker-specific delays."""

    delays = {"AAPL": 0.03, "MSFT": 0.01, "BTC": 0.02}
    await asyncio.sleep(delays[ticker])
    return {
        "ticker": ticker,
        "asset_type": "crypto" if ticker == "BTC" else "equity",
        "status": "ok",
        "summary": f"{ticker} summary",
        "trend": "bullish",
        "daily_change_pct": 1.25 if ticker != "BTC" else -0.5,
        "levels": {"support": 1.0, "resistance": 2.0},
        "indicators": {
            "last_close": 1.5,
            "sma_20": 1.4,
            "macd_line": 0.2,
            "macd_signal": 0.1,
            "price_change_pct": 9.9,
        },
        "ml_signal": None,
        "error": None,
    }


def _fake_macro_news(config: dict[str, object], now: datetime | None = None) -> dict[str, object]:
    """Return a stable macro-news payload for generator tests."""

    return {
        "status": "ok",
        "query": str(config["macro_query"]),
        "window_start": "2026-04-06T08:00:00+08:00",
        "window_end": "2026-04-07T08:00:00+08:00",
        "summary_points": [
            "Fed watch remains the top macro risk.",
            "Mega-cap tech leadership is still intact.",
            "Crypto sentiment is positive but volatile.",
        ],
        "sources": [
            {
                "title": "Fed watch remains the top macro risk.",
                "url": "https://example.com/fed",
                "source": "Reuters",
                "published_time": "2026-04-07T07:00:00+08:00",
                "snippet": "Markets remain cautious ahead of the next Fed signal.",
            }
        ],
        "error": None,
    }


def _fake_cio_summary(technical_sections, macro_news) -> dict[str, object]:
    """Return a stable CIO summary for generator tests."""

    return {
        "status": "ok",
        "text": f"{technical_sections[0]['ticker']} leads while macro risk centers on {macro_news['summary_points'][0]}",
        "error": None,
    }


def _fake_email_content(payload: dict[str, object]) -> dict[str, str]:
    """Return stable rendered email content for persistence tests."""

    digest_date = str(payload["meta"]["digest_date"])
    return {
        "subject": f"Daily Market Digest | {digest_date}",
        "text_body": "plain body",
        "html_body": "<html><body>html body</body></html>",
    }


def _fake_email_delivery(subject: str, text_body: str, html_body: str, config) -> dict[str, object]:
    """Return a stable delivery result without using SMTP."""

    return {
        "status": "skipped",
        "subject": subject,
        "recipients": list(config["recipients"]),
        "error": "missing smtp host",
    }


@pytest.mark.asyncio
async def test_generate_daily_digest_preserves_configured_ticker_order(
    monkeypatch, tmp_path, config
):
    """Generator should keep configured ticker order despite concurrent completion."""

    monkeypatch.setattr("app.digest.generator.MAX_CONCURRENT_TECHNICAL_SECTIONS", 3)
    monkeypatch.setattr(
        "app.digest.generator.build_technical_section", fake_out_of_order_section_builder
    )
    monkeypatch.setattr("app.digest.generator.build_macro_news_section", _fake_macro_news)
    monkeypatch.setattr("app.digest.generator.build_cio_summary", _fake_cio_summary)
    monkeypatch.setattr("app.digest.generator.render_digest_email", _fake_email_content)
    monkeypatch.setattr("app.digest.generator.send_digest_email", _fake_email_delivery)

    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)

    assert [section["ticker"] for section in payload["technical_sections"]] == [
        "AAPL",
        "MSFT",
        "BTC",
    ]
    for section in payload["technical_sections"]:
        assert "daily_change_pct" in section
    assert payload["run_id"].endswith("_daily_digest")


@pytest.mark.asyncio
async def test_generate_daily_digest_persists_json_text_and_html(monkeypatch, tmp_path, config):
    """Generator should persist the payload and both rendered email bodies."""

    monkeypatch.setattr(
        "app.digest.generator.build_technical_section", fake_out_of_order_section_builder
    )
    monkeypatch.setattr("app.digest.generator.build_macro_news_section", _fake_macro_news)
    monkeypatch.setattr("app.digest.generator.build_cio_summary", _fake_cio_summary)
    monkeypatch.setattr("app.digest.generator.render_digest_email", _fake_email_content)
    monkeypatch.setattr("app.digest.generator.send_digest_email", _fake_email_delivery)

    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)
    run_dir = base_dir / payload["run_id"]

    assert (run_dir / "digest.json").exists()
    assert (run_dir / "email.txt").read_text(encoding="utf-8") == "plain body"
    assert (run_dir / "email.html").read_text(
        encoding="utf-8"
    ) == "<html><body>html body</body></html>"
    persisted = json.loads((run_dir / "digest.json").read_text(encoding="utf-8"))
    assert (
        persisted["email"]["subject"] == "Daily Market Digest | " + payload["meta"]["digest_date"]
    )


@pytest.mark.asyncio
async def test_generate_daily_digest_uses_default_digests_directory(monkeypatch, tmp_path, config):
    """Generator should write under data/reports/digests when base_dir is omitted."""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.digest.generator.build_technical_section", fake_out_of_order_section_builder
    )
    monkeypatch.setattr("app.digest.generator.build_macro_news_section", _fake_macro_news)
    monkeypatch.setattr("app.digest.generator.build_cio_summary", _fake_cio_summary)
    monkeypatch.setattr("app.digest.generator.render_digest_email", _fake_email_content)
    monkeypatch.setattr("app.digest.generator.send_digest_email", _fake_email_delivery)

    payload = await generate_daily_digest(config)

    assert (tmp_path / "data" / "reports" / "digests" / payload["run_id"] / "digest.json").exists()


@pytest.mark.asyncio
async def test_generate_daily_digest_keeps_running_when_one_ticker_fails(
    monkeypatch, tmp_path, config
):
    """Generator should degrade one ticker to an error section without aborting the run."""

    async def flaky_builder(ticker: str, run_dir) -> dict[str, object]:
        if ticker == "BTC":
            raise RuntimeError("crypto timeout")
        return await fake_out_of_order_section_builder(ticker, run_dir)

    monkeypatch.setattr("app.digest.generator.build_technical_section", flaky_builder)
    monkeypatch.setattr("app.digest.generator.build_macro_news_section", _fake_macro_news)
    monkeypatch.setattr("app.digest.generator.build_cio_summary", _fake_cio_summary)
    monkeypatch.setattr("app.digest.generator.render_digest_email", _fake_email_content)
    monkeypatch.setattr("app.digest.generator.send_digest_email", _fake_email_delivery)

    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)

    failing = next(
        section for section in payload["technical_sections"] if section["ticker"] == "BTC"
    )
    assert failing["status"] == "error"
    assert failing["summary"] == "Technical snapshot unavailable for this run."
    assert failing["daily_change_pct"] is None
    assert "crypto timeout" in failing["error"]
    successful = next(
        section for section in payload["technical_sections"] if section["ticker"] == "AAPL"
    )
    assert successful["status"] == "ok"
    assert successful["daily_change_pct"] == 1.25
    assert successful["error"] is None


def test_build_macro_news_section_keeps_missing_timestamp_articles_when_needed(monkeypatch, config):
    """Macro news should backfill missing timestamps when strict filtering is too sparse."""

    raw_result = json.dumps(
        {
            "query": config["macro_query"],
            "count": 5,
            "source": "duckduckgo",
            "articles": [
                {
                    "title": "Fed signals patience as inflation cools",
                    "url": "https://example.com/fed",
                    "source": "Reuters",
                    "published_time": "2026-04-07T07:15:00+08:00",
                    "snippet": "Markets stayed cautious ahead of the next rate signal.",
                },
                {
                    "title": "Treasury yields rise after jobs data",
                    "url": "https://example.com/yields",
                    "source": "Bloomberg",
                    "published_time": None,
                    "snippet": "Bond markets repriced after another firm labor report.",
                },
                {
                    "title": "Bitcoin steadies as US stocks open mixed",
                    "url": "https://example.com/crypto",
                    "source": "CNBC",
                    "published_time": "",
                    "snippet": "Crypto held recent gains despite softer premarket breadth.",
                },
                {
                    "title": "Old macro story",
                    "url": "https://example.com/old",
                    "source": "WSJ",
                    "published_time": "2026-04-01T10:00:00+08:00",
                    "snippet": "This article is outside the digest window.",
                },
                {
                    "title": "Fed signals patience as inflation cools",
                    "url": "https://example.com/fed",
                    "source": "Reuters",
                    "published_time": "2026-04-07T07:15:00+08:00",
                    "snippet": "Duplicate should be removed.",
                },
            ],
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "app.digest.macro_news.search_realtime_news",
        SimpleNamespace(invoke=lambda params: raw_result),
    )

    now = datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    section = build_macro_news_section(config, now=now)

    assert section["status"] == "ok"
    assert 3 <= len(section["summary_points"]) <= 5
    assert len(section["sources"]) <= 8
    assert datetime.fromisoformat(section["window_start"]).tzinfo is not None
    assert datetime.fromisoformat(section["window_end"]).tzinfo is not None
    source_titles = {source["title"] for source in section["sources"]}
    assert "Treasury yields rise after jobs data" in source_titles
    assert "Bitcoin steadies as US stocks open mixed" in source_titles


@pytest.mark.asyncio
async def test_generate_daily_digest_payload_matches_required_top_level_contract(
    monkeypatch, tmp_path, config
):
    """Generator should emit the required digest contract and ISO timestamps."""

    monkeypatch.setattr(
        "app.digest.generator.build_technical_section", fake_out_of_order_section_builder
    )
    monkeypatch.setattr("app.digest.generator.build_macro_news_section", _fake_macro_news)
    monkeypatch.setattr("app.digest.generator.build_cio_summary", _fake_cio_summary)
    monkeypatch.setattr("app.digest.generator.render_digest_email", _fake_email_content)
    monkeypatch.setattr("app.digest.generator.send_digest_email", _fake_email_delivery)

    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)

    assert set(payload) >= {
        "module",
        "run_id",
        "meta",
        "tickers",
        "technical_sections",
        "macro_news",
        "cio_summary",
        "email",
    }
    assert payload["module"] == "daily_digest"
    assert set(payload["meta"]) >= {"generated_at_utc", "timezone", "scheduled_time", "digest_date"}
    assert set(payload["email"]) >= {"status", "subject", "recipients"}
    assert isinstance(payload["macro_news"]["summary_points"], list)
    assert datetime.fromisoformat(payload["macro_news"]["window_start"]).tzinfo is not None
    assert datetime.fromisoformat(payload["macro_news"]["window_end"]).tzinfo is not None
    for section in payload["technical_sections"]:
        assert section["asset_type"] in {"equity", "crypto"}
        assert "daily_change_pct" in section
    if payload["macro_news"]["status"] == "ok":
        assert payload["macro_news"]["error"] is None
    else:
        assert payload["macro_news"]["summary_points"] == []
