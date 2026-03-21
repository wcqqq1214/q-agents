from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

from app.social.reddit import tools as reddit_tools


def test_bnb_usd_routes_to_crypto_subreddit(monkeypatch) -> None:
    def _fake_get_reddit_discussion_via_json(
        *,
        asset: str,
        subreddits: Sequence[str],
        top_posts_limit: int,
        top_comments_per_post: int,
        time_filter: str,
    ) -> Tuple[str, Dict[str, Any]]:
        # No network: only return meta to let header render.
        return "", {"source": "json", "asset": asset, "subreddits": list(subreddits), "post_count": 0, "comment_count": 0}

    monkeypatch.setattr(reddit_tools, "_get_reddit_discussion_via_json", _fake_get_reddit_discussion_via_json)

    text = reddit_tools.get_reddit_discussion.invoke(
        {
            "asset": "BNB-USD",
            "max_chars": 2000,
            "top_posts_limit": 1,
            "top_comments_per_post": 1,
            "time_filter": "day",
        }
    )

    assert "Subreddits: CryptoCurrency" in text
    assert "wallstreetbets" not in text.lower()


def test_config_has_new_parameters():
    from app.social.reddit.tools import RedditIngestConfig

    config = RedditIngestConfig()
    assert hasattr(config, 'wide_fetch_limit')
    assert config.wide_fetch_limit == 50
    assert hasattr(config, 'final_posts_limit')
    assert config.final_posts_limit == 15
    assert config.top_comments_per_post == 3

