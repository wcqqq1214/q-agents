"""Tests for refreshed daily digest email rendering."""

from app.digest.render import render_digest_email


def test_render_digest_email_returns_price_board_and_detailed_macro_news():
    """Renderer should emit a compact ticker board and detailed macro items."""

    payload = {
        "meta": {
            "timezone": "Asia/Shanghai",
            "scheduled_time": "08:00",
            "digest_date": "2026-04-08",
        },
        "tickers": ["AAPL", "BTC"],
        "technical_sections": [
            {
                "ticker": "AAPL",
                "asset_type": "equity",
                "status": "ok",
                "summary": "unused",
                "trend": "bullish",
                "daily_change_pct": 1.234,
                "indicators": {"last_close": 254.48},
                "error": None,
            },
            {
                "ticker": "BTC",
                "asset_type": "crypto",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": None,
                "indicators": {"last_close": 68078.72},
                "error": None,
            },
        ],
        "macro_news": {
            "status": "ok",
            "window_start": "2026-04-07T08:00:00+08:00",
            "window_end": "2026-04-08T08:00:00+08:00",
            "summary_points": [],
            "sources": [
                {
                    "title": "Fed repricing hits risk assets",
                    "source": "Reuters",
                    "url": "https://example.com/fed",
                    "snippet": (
                        "Treasury yields climbed after stronger labor data. "
                        "Investors cut back expectations for near-term rate cuts."
                    ),
                },
                {
                    "title": "Bitcoin holds key support",
                    "source": "Bloomberg",
                    "url": "",
                    "snippet": "Crypto traded sideways after the macro selloff.",
                },
            ],
            "error": None,
        },
        "cio_summary": {
            "status": "ok",
            "text": "CIO stays unchanged.",
            "error": None,
        },
    }

    email = render_digest_email(payload)

    assert email["subject"] == "Daily Market Digest | 2026-04-08"
    assert "Daily Market Digest | 2026-04-08" in email["text_body"]
    assert "Schedule: 08:00 Asia/Shanghai" in email["text_body"]
    assert "AAPL 254.48 (+1.23%)" in email["text_body"]
    assert "BTC 68078.72 (--)" in email["text_body"]
    assert "(equity" not in email["text_body"]
    assert "(crypto" not in email["text_body"]
    assert "unused" not in email["text_body"]
    assert "1. Fed repricing hits risk assets" in email["text_body"]
    assert (
        "Summary: Treasury yields climbed after stronger labor data. "
        "Investors cut back expectations for near-term rate cuts."
    ) in email["text_body"]
    assert (
        "Summary: Crypto traded sideways after the macro selloff. "
        "This remains a macro watchpoint for today's cross-asset risk sentiment."
    ) in email["text_body"]
    assert "Source: Reuters" in email["text_body"]
    assert "Link: https://example.com/fed" in email["text_body"]
    assert "Link: Link unavailable" in email["text_body"]
    assert "CIO Summary" in email["text_body"]
    assert "CIO stays unchanged." in email["text_body"]
    assert "<html" in email["html_body"].lower()
    assert '<span style="color: #0a7f2e;">+1.23%</span>' in email["html_body"]
    assert '<span style="color: #6b7280;">--</span>' in email["html_body"]
    assert '<a href="https://example.com/fed">https://example.com/fed</a>' in email["html_body"]
    assert "CIO stays unchanged." in email["html_body"]


def test_render_digest_email_uses_deterministic_macro_news_fallbacks():
    """Renderer should keep deterministic news fallbacks and CIO fallback behavior."""

    payload = {
        "meta": {
            "timezone": "UTC",
            "scheduled_time": "06:30",
            "digest_date": "2026-04-08",
        },
        "tickers": ["ETH"],
        "technical_sections": [
            {
                "ticker": "ETH",
                "asset_type": "crypto",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": 0.0,
                "indicators": {"last_close": 2076.33},
                "error": None,
            }
        ],
        "macro_news": {
            "status": "ok",
            "window_start": "2026-04-07T06:30:00+00:00",
            "window_end": "2026-04-08T06:30:00+00:00",
            "summary_points": [],
            "sources": [
                {
                    "title": "Macro headline",
                    "source": "CNBC",
                    "url": None,
                    "snippet": None,
                },
                {
                    "title": "Second headline",
                    "source": "WSJ",
                    "url": "https://example.com/second",
                    "snippet": "Only one sentence here.",
                },
            ],
            "error": None,
        },
        "cio_summary": {
            "status": "error",
            "text": "",
            "error": "llm unavailable",
        },
    }

    email = render_digest_email(payload)

    assert email["subject"] == "Daily Market Digest | 2026-04-08"
    assert "ETH 2076.33 (0.00%)" in email["text_body"]
    assert (
        "Summary unavailable from the upstream news feed. "
        "This remains a macro watchpoint worth checking in the original article."
    ) in email["text_body"]
    assert (
        "Only one sentence here. "
        "This remains a macro watchpoint for today's cross-asset risk sentiment."
    ) in email["text_body"]
    assert "Link: Link unavailable" in email["text_body"]
    assert "Link: https://example.com/second" in email["text_body"]
    assert "Unavailable: llm unavailable" in email["text_body"]


def test_render_digest_email_cleans_markdown_snippets_and_derives_source_fallback():
    """Renderer should drop noisy markdown/title repeats and recover a readable source."""

    payload = {
        "meta": {
            "timezone": "UTC",
            "scheduled_time": "06:30",
            "digest_date": "2026-04-08",
        },
        "tickers": ["BTC"],
        "technical_sections": [
            {
                "ticker": "BTC",
                "asset_type": "crypto",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": -0.79,
                "indicators": {"last_close": 68315.16},
                "error": None,
            }
        ],
        "macro_news": {
            "status": "ok",
            "window_start": "2026-04-07T06:30:00+00:00",
            "window_end": "2026-04-08T06:30:00+00:00",
            "summary_points": [],
            "sources": [
                {
                    "title": "Rate jitters hit futures - MarketWatch",
                    "source": "",
                    "url": "https://www.marketwatch.com/story/futures-slip",
                    "snippet": (
                        "# Rate jitters hit futures - MarketWatch. "
                        "Stocks slipped before the open. "
                        "* Treasury yields climbed again."
                    ),
                }
            ],
            "error": None,
        },
        "cio_summary": {
            "status": "ok",
            "text": "CIO stays unchanged.",
            "error": None,
        },
    }

    email = render_digest_email(payload)

    assert (
        "Summary: Stocks slipped before the open. Treasury yields climbed again."
        in email["text_body"]
    )
    assert "Source: MarketWatch" in email["text_body"]


def test_render_digest_email_preserves_us_abbreviation_sentences():
    """Renderer should not split macro summaries inside common dotted abbreviations."""

    payload = {
        "meta": {
            "timezone": "UTC",
            "scheduled_time": "06:30",
            "digest_date": "2026-04-08",
        },
        "tickers": ["AAPL"],
        "technical_sections": [
            {
                "ticker": "AAPL",
                "asset_type": "equity",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": -0.45,
                "indicators": {"last_close": 254.48},
                "error": None,
            }
        ],
        "macro_news": {
            "status": "ok",
            "window_start": "2026-04-07T06:30:00+00:00",
            "window_end": "2026-04-08T06:30:00+00:00",
            "summary_points": [],
            "sources": [
                {
                    "title": "Jobs data jolts futures",
                    "source": "Reuters",
                    "url": "https://example.com/jobs",
                    "snippet": (
                        "The U.S. economy added 178,000 jobs in March. "
                        "U.S. stock futures were lower in early trade."
                    ),
                }
            ],
            "error": None,
        },
        "cio_summary": {
            "status": "ok",
            "text": "CIO stays unchanged.",
            "error": None,
        },
    }

    email = render_digest_email(payload)

    assert (
        "Summary: The U.S. economy added 178,000 jobs in March. "
        "U.S. stock futures were lower in early trade."
    ) in email["text_body"]
