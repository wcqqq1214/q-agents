"""Tests for Reddit ingestion/cleaning (Social Agent).

Run with:
    pytest -s tests/test_social_reddit_ingest.py

Notes:
    - This test prints a short excerpt of the fetched corpus to help manual
      verification of the ingestion quality (URLs removed, whitespace normalized,
      etc.).
    - If Reddit credentials are not configured (common in CI), tests are skipped.
"""

from __future__ import annotations

import pytest

from app.social.reddit import tools as reddit_tools


def _playwright_available() -> bool:
    try:
        # Import to verify that Playwright is installed and usable in this environment.
        from playwright.sync_api import sync_playwright  # type: ignore[import]

        return bool(sync_playwright)
    except Exception:
        return False


def test_get_reddit_discussion_returns_clean_text_and_respects_limit() -> None:
    try:
        text = reddit_tools.get_reddit_discussion.invoke(
            {
                "asset": "BTC",
                "max_chars": 8000,
                "top_posts_limit": 3,
                "top_comments_per_post": 2,
                "time_filter": "day",
            }
        )
    except Exception as exc:
        # If Playwright browsers are not installed or Reddit cannot be reached,
        # treat this as an environment limitation rather than a test failure.
        pytest.skip(f"Reddit/Playwright not usable in this environment: {exc}")

    assert isinstance(text, str)
    assert text.strip() != ""
    assert len(text) <= 8000

    # Extract header meta (first few lines).
    header_lines = text.splitlines()[:12]
    header = "\n".join(header_lines)
    assert "Asset:" in header
    assert "Subreddits:" in header
    assert "Source:" in header
    assert "PostCount:" in header
    assert "CommentCount:" in header

    # Manual verification helpers (use -s to see output).
    print("\n--- reddit_ingest_len ---")
    print(len(text))
    print("--- reddit_ingest_header ---")
    print(header)
    print("--- reddit_ingest_excerpt ---")
    print(text[:800])

