"""Lightweight Reddit JSON client (no official API / OAuth).

This module uses Reddit's public `.json` endpoints on `old.reddit.com` to fetch
subreddit listings and post comments as structured JSON. It is intended as the
**primary** ingestion path for the Social Agent because it is significantly
more stable than HTML scraping.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict, cast


class RedditPost(TypedDict, total=False):
    """A minimal post shape extracted from listing JSON."""

    title: str
    selftext: str
    permalink: str
    score: int
    created_utc: float


class RedditComment(TypedDict, total=False):
    """A minimal comment shape extracted from comments JSON."""

    body: str
    score: int
    created_utc: float


@dataclass(frozen=True)
class JsonFetchMeta:
    """Meta information about a JSON fetch run."""

    source: str  # "json"
    subreddit: str
    post_count: int
    comment_count: int
    errors: Tuple[str, ...] = ()


def _http_get_json(
    url: str,
    *,
    user_agent: str,
    timeout_s: float = 15.0,
    max_retries_429: int = 3,
) -> Any:
    """GET a URL and parse JSON with basic 429 backoff."""

    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json,text/plain,*/*",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt <= max_retries_429:
                sleep_s = (2 ** (attempt - 1)) + random.uniform(0.1, 0.6)
                time.sleep(sleep_s)
                continue
            raise


def fetch_subreddit_top_posts_json(
    subreddit: str,
    *,
    time_filter: str = "day",
    limit: int = 10,
    user_agent: str = "finance-agent-social/0.1",
) -> List[RedditPost]:
    """Fetch top posts for a subreddit from `old.reddit.com` as JSON."""

    sr = subreddit.strip().lstrip("/").replace("r/", "")
    qs = urllib.parse.urlencode({"t": time_filter, "limit": str(limit)})
    url = f"https://old.reddit.com/r/{sr}/top.json?{qs}"
    data = _http_get_json(url, user_agent=user_agent)
    children = cast(Dict[str, Any], data).get("data", {}).get("children", [])

    out: List[RedditPost] = []
    for ch in children:
        d = cast(Dict[str, Any], cast(Dict[str, Any], ch).get("data", {}))
        permalink = d.get("permalink") or ""
        if not isinstance(permalink, str) or not permalink:
            continue
        out.append(
            RedditPost(
                title=str(d.get("title") or ""),
                selftext=str(d.get("selftext") or ""),
                permalink=permalink,
                score=int(d.get("score") or 0),
                created_utc=float(d.get("created_utc") or 0.0),
            )
        )
    return out


def fetch_post_and_comments_json(
    permalink: str,
    *,
    limit: int = 50,
    user_agent: str = "finance-agent-social/0.1",
) -> Tuple[Optional[RedditPost], List[RedditComment]]:
    """Fetch a post and its comments via `{permalink}.json`."""

    pl = permalink if permalink.startswith("/") else f"/{permalink}"
    qs = urllib.parse.urlencode({"limit": str(limit)})
    url = f"https://old.reddit.com{pl}.json?{qs}"
    data = _http_get_json(url, user_agent=user_agent)
    if not isinstance(data, list) or len(data) < 2:
        return None, []

    post_listing = cast(Dict[str, Any], data[0])
    post_children = cast(Dict[str, Any], post_listing.get("data", {})).get("children", [])
    post: Optional[RedditPost] = None
    if post_children:
        pd = cast(Dict[str, Any], cast(Dict[str, Any], post_children[0]).get("data", {}))
        post = RedditPost(
            title=str(pd.get("title") or ""),
            selftext=str(pd.get("selftext") or ""),
            permalink=str(pd.get("permalink") or pl),
            score=int(pd.get("score") or 0),
            created_utc=float(pd.get("created_utc") or 0.0),
        )

    comment_listing = cast(Dict[str, Any], data[1])
    comment_children = cast(Dict[str, Any], comment_listing.get("data", {})).get("children", [])

    comments: List[RedditComment] = []
    for ch in comment_children:
        kind = cast(Dict[str, Any], ch).get("kind")
        if kind != "t1":
            continue
        cd = cast(Dict[str, Any], cast(Dict[str, Any], ch).get("data", {}))
        body = cd.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        if body in ("[removed]", "[deleted]"):
            continue
        comments.append(
            RedditComment(
                body=body,
                score=int(cd.get("score") or 0),
                created_utc=float(cd.get("created_utc") or 0.0),
            )
        )

    return post, comments


def select_top_comments(comments: Sequence[RedditComment], k: int = 3) -> List[str]:
    """Select top-k comment bodies by score."""

    usable = [c for c in comments if isinstance(c.get("body"), str) and c.get("body", "").strip()]
    usable.sort(key=lambda c: int(c.get("score") or 0), reverse=True)
    return [cast(str, c.get("body")) for c in usable[: max(0, k)]]
