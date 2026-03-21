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


def test_select_top_posts_globally():
    from app.social.reddit.tools import _select_top_posts_globally
    from app.social.reddit.json_client import RedditPost

    posts = [
        RedditPost(title="Post A", selftext="", permalink="/1", score=50, created_utc=1.0),
        RedditPost(title="Post B", selftext="", permalink="/2", score=200, created_utc=2.0),
        RedditPost(title="Post C", selftext="", permalink="/3", score=100, created_utc=3.0),
        RedditPost(title="Post D", selftext="", permalink="/4", score=150, created_utc=4.0),
    ]

    selected = _select_top_posts_globally(posts, limit=2)

    assert len(selected) == 2
    assert selected[0]["score"] == 200
    assert selected[1]["score"] == 150


def test_select_top_posts_limit_exceeds_available():
    from app.social.reddit.tools import _select_top_posts_globally
    from app.social.reddit.json_client import RedditPost

    posts = [
        RedditPost(title="Post A", selftext="", permalink="/1", score=50, created_utc=1.0),
    ]

    selected = _select_top_posts_globally(posts, limit=10)
    assert len(selected) == 1


def test_dynamic_filtering_pipeline_integration(monkeypatch):
    from app.social.reddit import tools as reddit_tools
    from app.social.reddit.json_client import RedditPost
    from typing import Any, Dict, List, Tuple

    # Mock fetch_subreddit_top_posts_json to return posts with asset mentions
    def mock_fetch_subreddit(subreddit, time_filter, limit, user_agent):
        if subreddit == "stocks":
            return [
                RedditPost(title="NVDA earnings beat", selftext="Great quarter", permalink="/stocks/1", score=200, created_utc=1.0),
                RedditPost(title="Market news", selftext="No specific stock", permalink="/stocks/2", score=50, created_utc=2.0),
            ]
        elif subreddit == "wallstreetbets":
            return [
                RedditPost(title="NVDA to the moon", selftext="Diamond hands", permalink="/wsb/1", score=300, created_utc=3.0),
            ]
        return []

    # Mock fetch_post_and_comments_json
    def mock_fetch_post(permalink, limit, user_agent):
        post = RedditPost(title="Mock", selftext="Mock", permalink=permalink, score=100, created_utc=1.0)
        comments = [{"body": "Comment 1", "score": 10}, {"body": "Comment 2", "score": 5}]
        return post, comments

    monkeypatch.setattr(reddit_tools, "fetch_subreddit_top_posts_json", mock_fetch_subreddit)
    monkeypatch.setattr(reddit_tools, "fetch_post_and_comments_json", mock_fetch_post)

    text, meta = reddit_tools._get_reddit_discussion_via_json(
        asset="NVDA",
        subreddits=["stocks", "wallstreetbets", "investing"],
        top_posts_limit=50,
        top_comments_per_post=3,
        time_filter="day"
    )

    # Verify metadata
    assert meta["posts_fetched_total"] >= 2  # At least 2 posts fetched
    assert meta["posts_after_filter"] == 2   # 2 posts mention NVDA
    assert meta["posts_selected"] == 2       # Both selected (limit not reached)
    assert meta["post_count"] == 2


def test_get_reddit_discussion_uses_new_config(monkeypatch):
    from app.social.reddit import tools as reddit_tools
    from typing import Any, Dict, Sequence, Tuple

    # Track what parameters were actually passed
    captured_params = {}

    def _fake_get_reddit_discussion_via_json(
        *,
        asset: str,
        subreddits: Sequence[str],
        top_posts_limit: int,
        top_comments_per_post: int,
        time_filter: str,
    ) -> Tuple[str, Dict[str, Any]]:
        # Capture parameters for verification
        captured_params["top_posts_limit"] = top_posts_limit
        captured_params["top_comments_per_post"] = top_comments_per_post
        return "", {
            "source": "json",
            "asset": asset,
            "subreddits": list(subreddits),
            "posts_fetched_total": 0,
            "posts_after_filter": 0,
            "posts_selected": 0,
            "post_count": 0,
            "comment_count": 0,
        }

    monkeypatch.setattr(reddit_tools, "_get_reddit_discussion_via_json", _fake_get_reddit_discussion_via_json)

    text = reddit_tools.get_reddit_discussion.invoke({
        "asset": "NVDA",
        "max_chars": 2000,
    })

    assert "Asset: NVDA" in text
    # Verify new parameters are passed correctly
    assert captured_params["top_posts_limit"] == 50, f"Expected top_posts_limit=50 (wide_fetch_limit), got {captured_params['top_posts_limit']}"
    assert captured_params["top_comments_per_post"] == 3, f"Expected top_comments_per_post=3, got {captured_params['top_comments_per_post']}"


