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
        # Return new metadata format
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

    monkeypatch.setattr(
        reddit_tools,
        "_get_reddit_discussion_via_json",
        _fake_get_reddit_discussion_via_json,
    )

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
    from app.social.reddit.tools import RedditIngestConfig, _asset_to_subreddits

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("NVDA", config)

    assert len(subreddits) == 5
    assert subreddits == [
        "stocks",
        "investing",
        "StockMarket",
        "wallstreetbets",
        "options",
    ]


def test_crypto_still_routes_to_one_subreddit():
    from app.social.reddit.tools import RedditIngestConfig, _asset_to_subreddits

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("BTC", config)

    assert len(subreddits) == 1
    assert subreddits[0] == "CryptoCurrency"


def test_stock_pair_routes_to_stock_subreddits():
    from app.social.reddit.tools import RedditIngestConfig, _asset_to_subreddits

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("AAPL-USD", config)

    assert len(subreddits) == 5
    assert "stocks" in subreddits


def test_lowercase_asset_routes_correctly():
    from app.social.reddit.tools import RedditIngestConfig, _asset_to_subreddits

    config = RedditIngestConfig()
    subreddits = _asset_to_subreddits("nvda", config)

    assert len(subreddits) == 5


def test_filter_posts_by_asset():
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="NVDA hits new high",
            selftext="Great earnings",
            permalink="/r/stocks/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="Market update",
            selftext="TSLA and NVDA moving",
            permalink="/r/stocks/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(
            title="AMD discussion",
            selftext="No mention of target",
            permalink="/r/stocks/3",
            score=80,
            created_utc=3.0,
        ),
        RedditPost(
            title="nvda options play",
            selftext="Calls looking good",
            permalink="/r/options/1",
            score=120,
            created_utc=4.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    assert len(filtered) == 3
    assert filtered[0]["title"] == "NVDA hits new high"
    assert filtered[1]["title"] == "Market update"
    assert filtered[2]["title"] == "nvda options play"


def test_filter_posts_empty_result():
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="AMD discussion",
            selftext="No mention of target",
            permalink="/r/stocks/1",
            score=100,
            created_utc=1.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")
    assert len(filtered) == 0


def test_select_top_posts_globally():
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _select_top_posts_globally

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
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _select_top_posts_globally

    posts = [
        RedditPost(title="Post A", selftext="", permalink="/1", score=50, created_utc=1.0),
    ]

    selected = _select_top_posts_globally(posts, limit=10)
    assert len(selected) == 1


def test_dynamic_filtering_pipeline_integration(monkeypatch):
    from app.social.reddit import tools as reddit_tools
    from app.social.reddit.json_client import RedditPost

    # Mock fetch_subreddit_top_posts_json to return posts with asset mentions
    def mock_fetch_subreddit(subreddit, time_filter, limit, user_agent):
        if subreddit == "stocks":
            return [
                RedditPost(
                    title="NVDA earnings beat",
                    selftext="Great quarter",
                    permalink="/stocks/1",
                    score=200,
                    created_utc=1.0,
                ),
                RedditPost(
                    title="Market news",
                    selftext="No specific stock",
                    permalink="/stocks/2",
                    score=50,
                    created_utc=2.0,
                ),
            ]
        elif subreddit == "wallstreetbets":
            return [
                RedditPost(
                    title="NVDA to the moon",
                    selftext="Diamond hands",
                    permalink="/wsb/1",
                    score=300,
                    created_utc=3.0,
                ),
            ]
        return []

    # Mock fetch_post_and_comments_json
    def mock_fetch_post(permalink, limit, user_agent):
        post = RedditPost(
            title="Mock",
            selftext="Mock",
            permalink=permalink,
            score=100,
            created_utc=1.0,
        )
        comments = [
            {"body": "Comment 1", "score": 10},
            {"body": "Comment 2", "score": 5},
        ]
        return post, comments

    monkeypatch.setattr(reddit_tools, "fetch_subreddit_top_posts_json", mock_fetch_subreddit)
    monkeypatch.setattr(reddit_tools, "fetch_post_and_comments_json", mock_fetch_post)

    text, meta = reddit_tools._get_reddit_discussion_via_json(
        asset="NVDA",
        subreddits=["stocks", "wallstreetbets", "investing"],
        top_posts_limit=50,
        top_comments_per_post=3,
        time_filter="day",
    )

    # Verify metadata
    assert meta["posts_fetched_total"] >= 2  # At least 2 posts fetched
    assert meta["posts_after_filter"] == 2  # 2 posts mention NVDA
    assert meta["posts_selected"] == 2  # Both selected (limit not reached)
    assert meta["post_count"] == 2


def test_get_reddit_discussion_uses_new_config(monkeypatch):
    from app.social.reddit import tools as reddit_tools

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

    monkeypatch.setattr(
        reddit_tools,
        "_get_reddit_discussion_via_json",
        _fake_get_reddit_discussion_via_json,
    )

    text = reddit_tools.get_reddit_discussion.invoke(
        {
            "asset": "NVDA",
            "max_chars": 2000,
        }
    )

    assert "Asset: NVDA" in text
    # Verify new parameters are passed correctly
    assert captured_params["top_posts_limit"] == 50, (
        f"Expected top_posts_limit=50 (wide_fetch_limit), got {captured_params['top_posts_limit']}"
    )
    assert captured_params["top_comments_per_post"] == 3, (
        f"Expected top_comments_per_post=3, got {captured_params['top_comments_per_post']}"
    )


def test_load_ticker_aliases():
    """测试别名配置加载"""
    from app.social.reddit.tools import _load_ticker_aliases

    aliases = _load_ticker_aliases()

    # 验证配置结构
    assert isinstance(aliases, dict)
    assert "NVDA" in aliases
    assert "aliases" in aliases["NVDA"]
    assert "type" in aliases["NVDA"]

    # 验证 NVDA 别名
    nvda_aliases = aliases["NVDA"]["aliases"]
    assert "NVDA" in nvda_aliases
    assert "Nvidia" in nvda_aliases
    assert "Nvidia Corp" in nvda_aliases

    # 验证 META 包含曾用名
    meta_aliases = aliases["META"]["aliases"]
    assert "FB" in meta_aliases
    assert "Facebook" in meta_aliases


def test_compile_ticker_regex():
    """测试正则表达式编译和缓存"""
    import re

    from app.social.reddit.tools import _compile_ticker_regex

    # 测试正常编译
    regex = _compile_ticker_regex("NVDA")
    assert regex is not None
    assert isinstance(regex, re.Pattern)

    # 测试匹配行为
    assert regex.search("NVDA is bullish")
    assert regex.search("$NVDA to the moon")
    assert regex.search("Nvidia earnings")
    assert regex.search("nvidia") is not None  # 大小写不敏感
    assert not regex.search("NVDAX")  # 词边界阻止误匹配

    # 测试缓存（同一对象）
    regex2 = _compile_ticker_regex("NVDA")
    assert regex is regex2


def test_compile_ticker_regex_fallback():
    """测试配置加载失败时的降级行为"""
    from unittest.mock import patch

    from app.social.reddit.tools import _compile_ticker_regex

    # Mock 配置加载失败
    with patch("app.social.reddit.tools._load_ticker_aliases", side_effect=FileNotFoundError):
        regex = _compile_ticker_regex("UNKNOWN")
        assert regex is not None
        # 应该回退到只匹配 ticker 本身
        assert regex.search("UNKNOWN")
        assert not regex.search("UnknownCompany")


def test_filter_with_ticker_exact_match():
    """测试精确匹配 ticker，避免误匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="NVDA hits new high",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="NVDAX is different",
            selftext="",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(
            title="Check NVDA performance",
            selftext="",
            permalink="/3",
            score=80,
            created_utc=3.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 应该只匹配 NVDA，不匹配 NVDAX
    assert len(filtered) == 2
    assert filtered[0]["title"] == "NVDA hits new high"
    assert filtered[1]["title"] == "Check NVDA performance"


def test_filter_with_company_name():
    """测试公司名称别名匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="Nvidia earnings beat",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="AMD discussion",
            selftext="",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(
            title="Nvidia Corp announces new GPU",
            selftext="",
            permalink="/3",
            score=80,
            created_utc=3.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 应该匹配 Nvidia 和 Nvidia Corp
    assert len(filtered) == 2
    assert "Nvidia" in filtered[0]["title"]
    assert "Nvidia Corp" in filtered[1]["title"]


def test_filter_with_cashtag():
    """测试 $NVDA 格式匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="$NVDA to the moon",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(title="Buying $TSLA", selftext="", permalink="/2", score=50, created_utc=2.0),
        RedditPost(
            title="$NVDA calls printing",
            selftext="",
            permalink="/3",
            score=80,
            created_utc=3.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 应该匹配 $NVDA
    assert len(filtered) == 2
    assert "$NVDA" in filtered[0]["title"]
    assert "$NVDA" in filtered[1]["title"]


def test_filter_no_false_positive():
    """测试词边界防止误匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="NVDAX is a different ticker",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="Visit mynvda.com",
            selftext="",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(title="NVDA_OPTIONS", selftext="", permalink="/3", score=80, created_utc=3.0),
        RedditPost(
            title="Real NVDA discussion",
            selftext="",
            permalink="/4",
            score=120,
            created_utc=4.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 只有最后一个应该匹配
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Real NVDA discussion"


def test_filter_case_insensitive():
    """测试大小写不敏感匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="nvidia is bullish",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="NVIDIA announces",
            selftext="",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(title="Nvidia Corp", selftext="", permalink="/3", score=80, created_utc=3.0),
        RedditPost(
            title="nvda options",
            selftext="",
            permalink="/4",
            score=120,
            created_utc=4.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 所有变体都应该匹配
    assert len(filtered) == 4


def test_filter_with_possessive():
    """测试所有格形式匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="Nvidia's earnings",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="NVDA's performance",
            selftext="",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(
            title="AMD's quarter",
            selftext="",
            permalink="/3",
            score=80,
            created_utc=3.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 应该匹配 Nvidia's 和 NVDA's
    assert len(filtered) == 2
    assert "Nvidia's" in filtered[0]["title"]
    assert "NVDA's" in filtered[1]["title"]


def test_filter_selftext_matching():
    """测试 selftext 字段匹配"""
    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="Market update",
            selftext="NVDA looking strong",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
        RedditPost(
            title="Tech stocks",
            selftext="AMD and TSLA moving",
            permalink="/2",
            score=50,
            created_utc=2.0,
        ),
        RedditPost(
            title="Discussion",
            selftext="Nvidia earnings beat expectations",
            permalink="/3",
            score=80,
            created_utc=3.0,
        ),
    ]

    filtered = _filter_posts_by_asset(posts, "NVDA")

    # 应该匹配 selftext 中的 NVDA 和 Nvidia
    assert len(filtered) == 2
    assert "NVDA" in filtered[0]["selftext"]
    assert "Nvidia" in filtered[1]["selftext"]


def test_filter_empty_aliases():
    """测试空别名列表返回空结果"""
    from unittest.mock import patch

    from app.social.reddit.json_client import RedditPost
    from app.social.reddit.tools import _filter_posts_by_asset

    posts = [
        RedditPost(
            title="UNKNOWN ticker",
            selftext="",
            permalink="/1",
            score=100,
            created_utc=1.0,
        ),
    ]

    # Mock _compile_ticker_regex 返回 None（模拟空别名列表）
    with patch("app.social.reddit.tools._compile_ticker_regex", return_value=None):
        filtered = _filter_posts_by_asset(posts, "UNKNOWN")
        assert len(filtered) == 0


def test_regex_caching():
    """测试正则表达式缓存机制"""
    from app.social.reddit.tools import _compile_ticker_regex

    # 清除缓存
    _compile_ticker_regex.cache_clear()

    # 第一次调用
    regex1 = _compile_ticker_regex("NVDA")
    cache_info1 = _compile_ticker_regex.cache_info()

    # 第二次调用（应该命中缓存）
    regex2 = _compile_ticker_regex("NVDA")
    cache_info2 = _compile_ticker_regex.cache_info()

    # 验证缓存命中
    assert regex1 is regex2
    assert cache_info2.hits == cache_info1.hits + 1
