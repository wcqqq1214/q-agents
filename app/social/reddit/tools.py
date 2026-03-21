"""Reddit ingestion tools for the Social Agent.

This module contains the implementation. The legacy module
`app/social/reddit_tools.py` re-exports from here for backward compatibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain_core.tools import tool

from app.social.reddit.json_client import (
    RedditPost,
    fetch_post_and_comments_json,
    fetch_subreddit_top_posts_json,
    select_top_comments,
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


@dataclass(frozen=True)
class RedditIngestConfig:
    """Configuration for Reddit ingestion and text normalization."""

    subreddit_crypto: str = "CryptoCurrency"
    # Deprecated: kept for backward compatibility, no longer used
    subreddit_stocks_primary: str = "wallstreetbets"
    subreddit_stocks_secondary: str = "stocks"

    # Wide fetch: posts per subreddit in initial fetch
    wide_fetch_limit: int = 50
    # Final output: posts after filtering and sorting
    final_posts_limit: int = 15
    # Comments per post (reduced from 5 to 3)
    top_comments_per_post: int = 3

    # Deprecated: will be replaced by wide_fetch_limit in Task 6
    top_posts_limit: int = 20

    time_filter: str = "day"
    max_chars: int = 24000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _asset_to_subreddits(asset: str, config: RedditIngestConfig) -> Sequence[str]:
    """Map an asset ticker to candidate subreddit names."""

    a = (asset or "").strip().upper()
    crypto = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK"}
    # Yahoo-style crypto pairs like BNB-USD should route to crypto subreddits.
    m = re.fullmatch(r"([A-Z]{2,10})-USD", a)
    base = m.group(1) if m else a
    if base in crypto:
        return [config.subreddit_crypto]
    # Stock assets route to 5 subreddits covering fundamentals and momentum
    return ["stocks", "investing", "StockMarket", "wallstreetbets", "options"]


def _filter_posts_by_asset(
    posts: List[RedditPost],
    asset: str
) -> List[RedditPost]:
    """Filter posts that mention the target asset ticker.

    Args:
        posts: List of Reddit posts (RedditPost TypedDict instances)
        asset: Asset ticker (e.g., "NVDA")

    Returns:
        Filtered list of posts that contain the asset ticker
    """
    asset_upper = asset.upper()
    filtered = []

    for post in posts:
        title = (post.get("title") or "").upper()
        selftext = (post.get("selftext") or "").upper()

        if asset_upper in title or asset_upper in selftext:
            filtered.append(post)

    return filtered


def _select_top_posts_globally(
    posts: List[RedditPost],
    limit: int
) -> List[RedditPost]:
    """Select top N posts by score across all subreddits.

    Args:
        posts: List of filtered posts
        limit: Maximum number of posts to select

    Returns:
        Top N posts sorted by score (descending)
    """
    sorted_posts = sorted(
        posts,
        key=lambda p: int(p.get("score") or 0),
        reverse=True
    )
    return sorted_posts[:limit]


def _clean_text(text: str) -> str:
    """Normalize Reddit text into a compact, LLM-friendly format."""

    t = text or ""
    t = _URL_RE.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _MULTI_NEWLINE_RE.sub("\n\n", t)
    t = _MULTI_SPACE_RE.sub(" ", t)
    lines = [ln.strip() for ln in t.split("\n")]
    return "\n".join(lines).strip()


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _format_post_block(
    *,
    title: str,
    body: str,
    comments: Sequence[str],
    score: Optional[int],
    created_utc: Optional[float],
) -> str:
    created = ""
    if created_utc:
        try:
            created_dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
            created = created_dt.isoformat()
        except Exception:
            created = ""

    header = f"Title: {title}".strip()
    meta_parts = []
    if score is not None:
        meta_parts.append(f"score={score}")
    if created:
        meta_parts.append(f"created={created}")
    meta = f"Meta: {', '.join(meta_parts)}" if meta_parts else ""

    chunks: List[str] = [header]
    if meta:
        chunks.append(meta)
    if body:
        chunks.append(f"Body:\n{body}")
    if comments:
        comment_lines = "\n".join([f"- {c}" for c in comments if c])
        if comment_lines:
            chunks.append(f"Top comments:\n{comment_lines}")
    return "\n".join(chunks).strip()


def _get_reddit_discussion_via_json(
    *,
    asset: str,
    subreddits: Sequence[str],
    top_posts_limit: int,
    top_comments_per_post: int,
    time_filter: str,
) -> Tuple[str, Dict[str, Any]]:
    user_agent = "finance-agent-social/0.1"
    blocks: List[str] = []
    post_count = 0
    comment_count = 0
    post_urls: List[str] = []
    errors: List[str] = []

    # Phase 1: Wide fetch - collect all posts from all subreddits
    all_posts: List[RedditPost] = []
    for sr in subreddits:
        try:
            posts = fetch_subreddit_top_posts_json(
                sr, time_filter=time_filter, limit=top_posts_limit, user_agent=user_agent
            )
            all_posts.extend(posts)
        except Exception as exc:
            errors.append(f"subreddit_fetch_failed:{sr}:{type(exc).__name__}")
            continue

    posts_fetched_total = len(all_posts)

    # Phase 2: Filter posts by asset ticker
    filtered_posts = _filter_posts_by_asset(all_posts, asset)
    posts_after_filter = len(filtered_posts)

    # Phase 3: Global sort and select top N
    # Use top_posts_limit as final_posts_limit for now (will use config later)
    selected_posts = _select_top_posts_globally(filtered_posts, limit=top_posts_limit)
    posts_selected = len(selected_posts)

    # Phase 4: Fetch details for selected posts only
    for p in selected_posts:
        permalink = str(p.get("permalink") or "")
        if permalink:
            post_urls.append(f"https://old.reddit.com{permalink}")

        try:
            post, comments = fetch_post_and_comments_json(
                permalink,
                limit=50,
                user_agent=user_agent,
            )
        except Exception as exc:
            errors.append(f"post_detail_failed:{type(exc).__name__}")
            continue

        src = post or p
        title = _clean_text(str(src.get("title") or ""))
        body = _clean_text(str(src.get("selftext") or ""))
        top_comments = select_top_comments(comments, k=top_comments_per_post)
        top_comments_clean = [_clean_text(c) for c in top_comments if c]

        block = _format_post_block(
            title=title,
            body=body,
            comments=top_comments_clean,
            score=int(src.get("score") or 0) if src.get("score") is not None else None,
            created_utc=float(src.get("created_utc") or 0.0) if src.get("created_utc") else None,
        )
        if block:
            blocks.append(block)
            blocks.append("")
            post_count += 1
            comment_count += len(top_comments_clean)

    text = _clean_text("\n".join(blocks))
    meta: Dict[str, Any] = {
        "source": "json",
        "asset": asset,
        "subreddits": list(subreddits),
        "posts_fetched_total": posts_fetched_total,
        "posts_after_filter": posts_after_filter,
        "posts_selected": posts_selected,
        "post_count": post_count,
        "comment_count": comment_count,
        "post_urls": post_urls[:min(len(post_urls), top_posts_limit)],
        "errors": errors,
    }
    return text, meta


@tool("get_reddit_discussion")
def get_reddit_discussion(
    asset: str,
    *,
    max_chars: int = 24000,
    top_posts_limit: int = 20,
    top_comments_per_post: int = 5,
    time_filter: str = "day",
    subreddit_override: Optional[str] = None,
) -> str:
    """Fetch and normalize recent Reddit discussion about an asset ticker (JSON-first).

    This tool is the Social Agent's Reddit ingestion entry point. It implements
    the blueprint semantics (24h top posts + top comments + text cleaning) but
    uses a JSON-first strategy for stability:

    - Primary: `old.reddit.com/*.json` public endpoints (no OAuth).
    - Fallback: Playwright HTML scraping when JSON fails.

    The returned text begins with a short header that includes ingestion meta
    fields (source, post_count, comment_count) so downstream steps can diagnose
    variability and stability.

    Args:
        asset: Asset identifier such as "BTC" or "NVDA".
        max_chars: Maximum characters of the returned corpus after cleaning.
        top_posts_limit: Target number of top posts to fetch per subreddit.
        top_comments_per_post: Target number of top comments per post.
        time_filter: Reddit top time window, typically "day".
        subreddit_override: Optional explicit subreddit (without "r/").

    Returns:
        A cleaned, concatenated Reddit discussion corpus string suitable for LLM input.
    """

    normalized_asset = (asset or "").strip().upper()
    if not normalized_asset:
        raise RuntimeError("asset is empty; provide a ticker such as 'BTC' or 'NVDA'.")

    config = RedditIngestConfig(
        time_filter=time_filter,
        max_chars=max_chars,
    )

    subreddits = (
        [subreddit_override.strip()]
        if subreddit_override
        else list(_asset_to_subreddits(normalized_asset, config))
    )

    text = ""
    meta: Dict[str, Any] = {}

    # JSON-only strategy with up to 5 retry attempts; we never fall back to Playwright
    last_exc: Optional[Exception] = None
    for attempt in range(5):
        try:
            text, meta = _get_reddit_discussion_via_json(
                asset=normalized_asset,
                subreddits=subreddits,
                top_posts_limit=config.wide_fetch_limit,
                top_comments_per_post=config.top_comments_per_post,
                time_filter=config.time_filter,
            )
            if text.strip():
                break
        except Exception as exc:
            last_exc = exc
            continue

    if (not text.strip()) and not meta:
        meta = {
            "source": "json",
            "asset": normalized_asset,
            "subreddits": list(subreddits),
            "post_count": 0,
            "comment_count": 0,
            "errors": [
                f"json_all_attempts_failed:{type(last_exc).__name__}" if last_exc else "json_all_attempts_failed"
            ],
        }

    header = (
        f"Asset: {normalized_asset}\n"
        f"Window: last 24h (time_filter={config.time_filter})\n"
        f"Subreddits: {', '.join(subreddits)}\n"
        f"Source: {meta.get('source', 'unknown')}\n"
        f"PostCount: {int(meta.get('post_count') or 0)}\n"
        f"CommentCount: {int(meta.get('comment_count') or 0)}\n"
        f"GeneratedAt(UTC): {_utc_now().replace(microsecond=0).isoformat()}\n"
    ).strip()

    combined = _clean_text("\n".join([header, "", text]).strip())
    if not combined.strip():
        combined = _clean_text(
            "\n".join(
                [header, "", "No posts fetched from Reddit for the given asset and subreddits."]
            )
        )
    return _truncate(combined, config.max_chars)


