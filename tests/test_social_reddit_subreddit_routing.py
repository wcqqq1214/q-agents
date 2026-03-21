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
    assert config.wide_fetch_limit == 50
    assert config.final_posts_limit == 15
    assert config.top_comments_per_post == 3


def test_stock_routes_to_five_subreddits():
    from app.social.reddit.tools import _asset_to_subreddits, RedditIngestConfig

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("NVDA", config)

    assert len(subreddits) == 5
    assert subreddits == ["stocks", "investing", "StockMarket", "wallstreetbets", "options"]


def test_crypto_still_routes_to_one_subreddit():
    from app.social.reddit.tools import _asset_to_subreddits, RedditIngestConfig

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("BTC", config)

    assert len(subreddits) == 1
    assert subreddits[0] == "CryptoCurrency"


def test_stock_pair_routes_to_stock_subreddits():
    from app.social.reddit.tools import _asset_to_subreddits, RedditIngestConfig

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("AAPL-USD", config)

    assert len(subreddits) == 5
    assert "stocks" in subreddits


def test_lowercase_asset_routes_correctly():
    from app.social.reddit.tools import _asset_to_subreddits, RedditIngestConfig

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("nvda", config)

    assert len(subreddits) == 5


def test_filter_posts_by_asset():
    from app.social.reddit.tools import _filter_posts_by_asset
    from app.social.reddit.json_client import RedditPost

    posts = [
        RedditPost(title="NVDA hits new high", selftext="Great earnings", permalink="/r/stocks/1", score=100, created_utc=1.0),
        RedditPost(title="Market update", selftext="TSLA and NVDA moving", permalink="/r/stocks/2", score=50, created_utc=2.0),
        RedditPost(title="AMD discussion", selftext="No mention of target", permalink="/r/stocks/3", score=80, created_utc=3.0),
        RedditPost(title="nvda options play", selftext="Calls looking good", permalink="/r/options/1", score=120, created_utc=4.0),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    assert len(filtered) == 3
    assert filtered[0]["title"] == "NVDA hits new high"
    assert filtered[1]["title"] == "Market update"
    assert filtered[2]["title"] == "nvda options play"


def test_filter_posts_empty_result():
    from app.social.reddit.tools import _filter_posts_by_asset
    from app.social.reddit.json_client import RedditPost

    posts = [
        RedditPost(title="AMD discussion", selftext="No mention of target", permalink="/r/stocks/1", score=100, created_utc=1.0),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")
    assert len(filtered) == 0


