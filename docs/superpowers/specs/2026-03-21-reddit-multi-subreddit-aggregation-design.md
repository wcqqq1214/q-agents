# Reddit多板块聚合与动态过滤设计文档

**日期**: 2026-03-21
**状态**: 待审核

## 概述

扩展Reddit散户情绪抓取功能，将股票资产的subreddit覆盖从2个（wallstreetbets + stocks）扩展到5个，并实现动态过滤管道以提高内容相关性和信噪比。

## 背景

当前实现仅抓取2个subreddit，无法全面覆盖散户情绪的不同维度：
- **缺失基本面讨论**：r/investing、r/StockMarket等理性讨论区未被覆盖
- **缺失期权流信号**：r/options的专业讨论未被利用
- **内容相关性低**：固定抓取top 20帖子，可能包含大量与目标资产无关的内容

## 目标

1. 扩展股票资产的subreddit覆盖到5个板块
2. 实现动态过滤管道，确保只抓取与目标资产相关的帖子
3. 通过全局排序优化内容质量，而非简单的per-subreddit平均分配
4. 保持向后兼容，不影响加密货币资产的现有逻辑

## 设计方案

### 1. Subreddit路由扩展

**修改位置**: `app/social/reddit/tools.py` 中的 `_asset_to_subreddits()` 函数

**新路由规则**:

```python
# 加密货币资产 → CryptoCurrency (保持不变)
crypto_tickers = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK"}
if asset in crypto_tickers:
    return ["CryptoCurrency"]

# 股票资产 → 5个subreddit (新增)
return ["stocks", "investing", "StockMarket", "wallstreetbets", "options"]
```

**理由**:
- `stocks`, `investing`, `StockMarket`: 基本面与大盘情绪（高信噪比）
- `wallstreetbets`, `options`: 短期动能与期权流（高敏感度）

### 2. 配置参数调整

**修改位置**: `RedditIngestConfig` 数据类

**新增参数**:
```python
@dataclass(frozen=True)
class RedditIngestConfig:
    subreddit_crypto: str = "CryptoCurrency"
    # 移除 subreddit_stocks_primary 和 subreddit_stocks_secondary

    # 新增：宽泛抓取阶段的每个subreddit帖子数
    wide_fetch_limit: int = 50

    # 新增：最终输出的帖子数（全局排序后）
    final_posts_limit: int = 15

    # 修改：每篇帖子的评论数从5改为3
    top_comments_per_post: int = 3

    time_filter: str = "day"
    max_chars: int = 24000
```

### 3. 动态过滤管道

**核心流程**:

```
[宽泛抓取] → [内容过滤] → [全局排序] → [截断选择] → [详情抓取]
```

#### 3.1 宽泛抓取阶段

**实现**: 修改 `_get_reddit_discussion_via_json()` 函数

- 对每个subreddit调用 `fetch_subreddit_top_posts_json()`
- 使用 `wide_fetch_limit` (默认50) 而非当前的 `top_posts_limit` (20)
- 只获取帖子元数据（title, selftext, score, permalink），不抓取评论
- 收集所有subreddit的帖子到一个列表中

#### 3.2 内容过滤阶段

**新增函数**: `_filter_posts_by_asset(posts, asset)`

```python
def _filter_posts_by_asset(
    posts: List[RedditPost],
    asset: str
) -> List[RedditPost]:
    """Filter posts that mention the target asset ticker.

    Args:
        posts: List of Reddit posts with title and selftext
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
```

**匹配规则**:
- 大小写不敏感的字符串包含检查
- 匹配范围：标题（title）+ 正文（selftext）
- 当前版本仅支持简单字符串匹配，后续可扩展为别名/正则匹配

#### 3.3 全局排序与选择

**新增函数**: `_select_top_posts_globally(posts, limit)`

```python
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
```

#### 3.4 详情抓取阶段

**修改**: 只对选中的帖子调用 `fetch_post_and_comments_json()`

- 遍历 `_select_top_posts_globally()` 返回的帖子列表
- 对每篇帖子抓取完整内容和top 3评论
- 格式化为文本块

### 4. 元数据扩展

**新增字段**:

```python
meta = {
    "source": "json",
    "asset": "NVDA",
    "subreddits": ["stocks", "investing", "StockMarket", "wallstreetbets", "options"],

    # 新增：过滤管道的统计信息
    "posts_fetched_total": 250,      # 宽泛抓取的总数 (5 * 50)
    "posts_after_filter": 45,        # 过滤后匹配的数量
    "posts_selected": 15,            # 最终选择的数量

    # 保持兼容
    "post_count": 15,                # 实际输出的帖子数
    "comment_count": 45,             # 实际输出的评论数 (15 * 3)
    "post_urls": [...],
    "errors": []
}
```

**用途**:
- 诊断过滤效果（如果 `posts_after_filter` 很低，说明ticker匹配率低）
- 监控数据质量（如果 `posts_fetched_total` 远小于预期，说明某些subreddit抓取失败）

### 5. 错误处理

**Subreddit级别失败**:
- 如果某个subreddit的 `fetch_subreddit_top_posts_json()` 抛出异常，记录错误但继续处理其他subreddit
- 在 `meta["errors"]` 中添加 `"subreddit_fetch_failed:stocks:HTTPError"`

**过滤后无结果**:
- 如果 `_filter_posts_by_asset()` 返回空列表，不视为错误
- 返回包含header的空报告，元数据中 `posts_after_filter: 0`

**单个帖子详情抓取失败**:
- 跳过该帖子，继续处理下一个
- 在 `meta["errors"]` 中记录失败数量

## 实现细节

### 修改文件清单

1. **app/social/reddit/tools.py**
   - 修改 `_asset_to_subreddits()`: 返回5个subreddit
   - 修改 `RedditIngestConfig`: 新增参数，移除旧参数
   - 新增 `_filter_posts_by_asset()`: 内容过滤函数
   - 新增 `_select_top_posts_globally()`: 全局排序函数
   - 修改 `_get_reddit_discussion_via_json()`: 实现动态过滤管道

2. **tests/test_social_reddit_subreddit_routing.py**
   - 更新现有测试以匹配新的路由逻辑
   - 新增测试：验证5个subreddit路由
   - 新增测试：验证过滤和排序逻辑

### 向后兼容性

- 加密货币资产的路由逻辑保持不变
- `get_reddit_discussion()` 工具的API签名不变
- 元数据格式向后兼容（新增字段，不删除旧字段）
- 现有调用方无需修改代码

### 性能影响

**预期时间**:
- 宽泛抓取：5个subreddit × 1-2秒 = 5-10秒
- 过滤与排序：< 0.1秒（内存操作）
- 详情抓取：15篇 × 0.5秒 = 7-8秒
- **总计**: 12-18秒（vs 当前的8-10秒）

**优化考虑**:
- 当前串行执行以避免429限流
- 未来可考虑并发抓取（需要实现速率限制）

## 测试策略

### 单元测试

1. **路由测试**
   - 验证股票资产返回5个subreddit
   - 验证加密货币资产返回1个subreddit

2. **过滤测试**
   - 验证ticker匹配逻辑（标题、正文、大小写）
   - 验证空列表处理

3. **排序测试**
   - 验证按score降序排列
   - 验证limit截断逻辑

### 集成测试

1. **端到端测试**
   - Mock Reddit API，验证完整管道
   - 验证元数据字段正确性

2. **真实API测试**
   - 使用真实ticker（如"NVDA"）调用工具
   - 验证返回内容的相关性和格式

## 未来扩展

1. **增强匹配逻辑**
   - 支持公司名称别名（NVDA → "Nvidia", "Jensen"）
   - 支持正则表达式（$TICKER格式）
   - 支持配置文件定义别名映射

2. **动态subreddit选择**
   - 根据股票特征（市值、波动率）选择不同的subreddit组合
   - 支持用户自定义subreddit列表

3. **并发优化**
   - 实现速率限制器
   - 并发抓取多个subreddit

4. **缓存机制**
   - 缓存subreddit列表数据（TTL: 5分钟）
   - 减少重复请求

## 风险与缓解

**风险1**: 过滤后帖子数量不足
- **缓解**: 如果 `posts_after_filter < final_posts_limit`，输出所有匹配的帖子，不强制达到limit

**风险2**: Reddit API限流
- **缓解**: 保持串行执行，添加重试逻辑（已有）

**风险3**: 某些subreddit长期不可用
- **缓解**: 错误处理机制确保部分失败不影响整体结果

## 总结

本设计通过扩展subreddit覆盖和实现动态过滤管道，显著提升了Reddit情绪抓取的全面性和相关性。核心改进包括：

1. **覆盖面**: 从2个subreddit扩展到5个，覆盖基本面和动能两个维度
2. **相关性**: 通过ticker过滤确保所有帖子都与目标资产相关
3. **质量**: 通过全局排序优先选择高质量内容
4. **可扩展性**: 过滤和排序逻辑独立封装，便于未来增强

实现方案保持向后兼容，风险可控，预期能够为下游的情绪分析提供更高质量的输入数据。
