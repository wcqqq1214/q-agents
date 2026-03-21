# Reddit Ticker 别名匹配优化设计文档

**日期**: 2026-03-21
**状态**: 待审核

## 概述

优化 Reddit 情绪抓取功能的文本匹配逻辑，从简单子串匹配升级为"别名字典 + 正则词边界匹配"，解决误匹配和漏匹配问题。

## 背景

当前 `_filter_posts_by_asset()` 函数使用简单的子串匹配（`asset_upper in title`），存在两个核心问题：

### 问题 1：误匹配
- **现象**：搜索 "NVDA" 会匹配到 "NVDAX"
- **原因**：子串匹配无法识别词边界
- **影响**：引入无关数据，污染情绪分析结果

### 问题 2：漏匹配
- **现象**：Reddit 用户使用 "$NVDA"、"Nvidia"、"FB"（META 曾用名）等变体
- **原因**：只匹配标准 ticker，无法覆盖别名
- **影响**：丢失大量有效讨论，召回率低

## 目标

1. **消除误匹配**：使用词边界正则表达式，确保精确匹配
2. **提升召回率**：支持 ticker、公司简称、曾用名等常见别名
3. **兼容 Reddit 特性**：支持 Cashtag 格式（$NVDA）
4. **保持性能**：对于 9 个资产的规模，匹配延迟 < 1ms
5. **易于维护**：别名配置与代码分离，支持快速更新

## 设计方案

### 1. 别名配置文件

**文件位置**: `app/social/reddit/ticker_aliases.json`

**格式**: 结构化 JSON，支持未来扩展元数据

```json
{
  "NVDA": {
    "aliases": ["NVDA", "Nvidia", "Nvidia Corp"],
    "type": "stock"
  },
  "AAPL": {
    "aliases": ["AAPL", "Apple"],
    "type": "stock"
  },
  "MSFT": {
    "aliases": ["MSFT", "Microsoft", "Microsoft Corp"],
    "type": "stock"
  },
  "GOOGL": {
    "aliases": ["GOOGL", "GOOG", "Google", "Alphabet"],
    "type": "stock"
  },
  "AMZN": {
    "aliases": ["AMZN", "Amazon"],
    "type": "stock"
  },
  "TSLA": {
    "aliases": ["TSLA", "Tesla"],
    "type": "stock"
  },
  "META": {
    "aliases": ["META", "Meta", "Facebook", "FB"],
    "type": "stock"
  },
  "BTC": {
    "aliases": ["BTC", "Bitcoin"],
    "type": "crypto"
  },
  "ETH": {
    "aliases": ["ETH", "Ethereum"],
    "type": "crypto"
  }
}
```

**设计原则**:
- **只包含高确定性别名**：ticker、公司简称、曾用名
- **不包含口语化表达**：如 "Jensen's company"（维护成本高、误杀率高）
- **不包含 CEO/产品名**：如 "Jensen Huang"、"ChatGPT"（情绪错配风险）

**边界划分**:
- **Python 正则层**：高精度过滤，快速排除无关内容
- **LLM 层**：理解复杂语义，处理隐式提及和情绪分析

### 2. 核心函数实现

#### 2.1 别名加载函数

**新增函数**: `_load_ticker_aliases()`

**位置**: `app/social/reddit/tools.py`（插入到 `_filter_posts_by_asset()` 之前）

```python
from functools import lru_cache
from pathlib import Path
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def _load_ticker_aliases() -> Dict[str, Dict[str, Any]]:
    """加载 ticker 别名配置（带缓存）。

    使用 lru_cache 确保配置文件只加载一次，避免重复 I/O。

    Returns:
        字典，键为 ticker（大写），值为配置对象：
        {
            "aliases": List[str],  # 别名列表
            "type": str            # "stock" 或 "crypto"
        }

    Raises:
        FileNotFoundError: 配置文件不存在
        json.JSONDecodeError: 配置文件格式错误
    """
    config_path = Path(__file__).parent / "ticker_aliases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)
```

**设计要点**:
- `@lru_cache(maxsize=1)`: 配置文件只加载一次，后续调用直接返回缓存
- 使用 `Path(__file__).parent`: 相对路径，确保在任何工作目录下都能找到配置文件
- 异常向上传播，由调用方处理

#### 2.1.1 正则编译缓存函数

**新增函数**: `_compile_ticker_regex()`

**位置**: `app/social/reddit/tools.py`（插入到 `_filter_posts_by_asset()` 之前）

```python
@lru_cache(maxsize=128)
def _compile_ticker_regex(asset: str) -> Optional[re.Pattern]:
    """编译并缓存 ticker 的正则表达式。

    Args:
        asset: 资产代码（如 "NVDA"）

    Returns:
        编译后的正则表达式对象，如果别名列表为空则返回 None
    """
    asset_upper = asset.upper()

    try:
        aliases_config = _load_ticker_aliases()
        ticker_config = aliases_config.get(asset_upper, {})
        aliases = ticker_config.get("aliases", [asset_upper])
    except Exception as e:
        logger.warning(f"Failed to load ticker aliases for {asset_upper}: {e}, falling back to simple matching")
        aliases = [asset_upper]

    # 验证别名列表非空
    if not aliases:
        logger.warning(f"Empty alias list for {asset_upper}")
        return None

    # 构建正则表达式：\$?\b(NVDA|Nvidia|Nvidia Corp)\b
    escaped_aliases = [re.escape(alias) for alias in aliases]
    pattern = r'\$?\b(' + '|'.join(escaped_aliases) + r')\b'
    return re.compile(pattern, re.IGNORECASE)
```

**设计要点**:
- `@lru_cache(maxsize=128)`: 缓存每个 ticker 的编译后正则，避免重复编译
- 空别名列表验证：返回 `None` 而非构建无效正则
- 日志记录：配置加载失败时记录警告，便于调试

#### 2.2 改造过滤函数

**修改函数**: `_filter_posts_by_asset()`

**位置**: `app/social/reddit/tools.py`（第 69-92 行）

```python
def _filter_posts_by_asset(
    posts: List[RedditPost],
    asset: str
) -> List[RedditPost]:
    """使用别名字典和正则词边界过滤帖子。

    匹配规则：
    1. 通过 _compile_ticker_regex() 获取缓存的正则表达式
    2. 正则模式：\$?\b(alias1|alias2|...)\b
       - \$? : 可选的美元符号前缀（支持 $NVDA 格式）
       - \b  : 词边界，避免误匹配（NVDA 不会匹配 NVDAX）
       - re.IGNORECASE : 忽略大小写
    3. 在帖子的 title 和 selftext 中搜索匹配

    注意：与旧实现的行为变化
    - 旧实现：将文本转为大写后匹配（title.upper()）
    - 新实现：使用 re.IGNORECASE，保持原文本不变
    - 影响：无功能差异，但正则匹配更高效

    Args:
        posts: Reddit 帖子列表（RedditPost TypedDict 实例）
        asset: 资产代码（如 "NVDA"）

    Returns:
        匹配的帖子列表
    """
    # 获取编译后的正则表达式（带缓存）
    regex = _compile_ticker_regex(asset)
    if regex is None:
        # 别名列表为空，无法匹配
        return []

    filtered = []
    for post in posts:
        title = post.get("title") or ""
        selftext = post.get("selftext") or ""
        combined_text = f"{title} {selftext}"

        match = regex.search(combined_text)
        if match:
            filtered.append(post)

    return filtered
```

**关键特性**:
1. **正则缓存**: 通过 `_compile_ticker_regex()` 避免重复编译
2. **词边界匹配** (`\b`): 避免误匹配
   - ✅ "NVDA is bullish" → 匹配
   - ❌ "NVDAX is bullish" → 不匹配
   - ✅ "Nvidia's earnings" → 匹配（所有格形式）
3. **Cashtag 支持** (`\$?`): 兼容 Reddit 习惯
   - ✅ "$NVDA to the moon" → 匹配
4. **大小写不敏感** (`re.IGNORECASE`): 覆盖各种写法
   - ✅ "nvidia", "NVIDIA", "Nvidia" → 都匹配
5. **空别名处理**: 返回空列表而非抛出异常

### 3. 正则表达式示例

以 NVDA 为例，生成的正则表达式为：

```regex
\$?\b(NVDA|Nvidia|Nvidia\ Corp)\b
```

**匹配示例**:
- ✅ "NVDA earnings beat expectations"
- ✅ "$NVDA to the moon 🚀"
- ✅ "Nvidia just announced new GPUs"
- ✅ "Nvidia Corp reported strong revenue"
- ✅ "I'm bullish on nvidia" (大小写不敏感)
- ❌ "NVDAX is a different ticker" (词边界阻止)
- ❌ "mynvda.com" (词边界阻止)

### 4. 性能分析

**时间复杂度**:
- 配置加载: O(1)（缓存后）
- 正则编译: O(1)（缓存后，首次调用 O(m)，m 为别名总长度）
- 文本匹配: O(n * k)，n 为帖子数，k 为平均文本长度

**实际性能**:
- 9 个资产，平均 3 个别名/资产
- 正则编译（首次）: < 0.1ms
- 正则编译（缓存命中）: < 0.001ms
- 单帖匹配: < 0.01ms
- 50 篇帖子过滤: < 1ms

**性能优化**:
- `@lru_cache` 确保每个 ticker 的正则只编译一次
- 对于重复调用同一 ticker（如连续抓取多天数据），缓存命中率接近 100%
- 缓存大小 128 足以覆盖所有可能的 ticker

### 5. 错误处理

**配置文件缺失**:
- 捕获 `FileNotFoundError`，回退到 `[asset_upper]`
- 记录 warning 日志：`"Failed to load ticker aliases: FileNotFoundError, falling back to simple matching"`
- 系统以降级模式运行，不中断服务

**配置文件格式错误**:
- 捕获 `json.JSONDecodeError`，回退到 `[asset_upper]`
- 记录 warning 日志：`"Failed to load ticker aliases: JSONDecodeError, falling back to simple matching"`
- 便于运维人员快速定位配置问题

**别名列表为空**:
- `_compile_ticker_regex()` 返回 `None`
- `_filter_posts_by_asset()` 返回空列表 `[]`
- 记录 warning 日志：`"Empty alias list for {ticker}"`

**正则编译失败**:
- 理论上不会发生（`re.escape()` 确保安全）
- 如果发生，Python 会抛出 `re.error`，由上层捕获

## 实现细节

### 修改文件清单

1. **app/social/reddit/ticker_aliases.json** (新增)
   - 别名配置文件
   - 包含 Magnificent Seven + BTC + ETH

2. **app/social/reddit/tools.py** (修改)
   - 在文件顶部添加 import: `import logging` (注：`import re`, `import json` 已存在)
   - 新增 `logger = logging.getLogger(__name__)` (第 26 行之前插入)
   - 新增 `_load_ticker_aliases()` 函数（第 68 行之前插入）
   - 新增 `_compile_ticker_regex()` 函数（第 68 行之前插入）
   - 修改 `_filter_posts_by_asset()` 函数（第 69-92 行替换）

3. **tests/test_social_reddit_subreddit_routing.py** (修改)
   - 新增测试用例：
     - `test_filter_with_ticker_exact_match`: 验证 ticker 精确匹配
     - `test_filter_with_company_name`: 验证公司名匹配
     - `test_filter_with_cashtag`: 验证 $NVDA 格式
     - `test_filter_no_false_positive`: 验证词边界（NVDA vs NVDAX）
     - `test_filter_case_insensitive`: 验证大小写不敏感
     - `test_filter_with_possessive`: 验证所有格形式（"Nvidia's"）
     - `test_filter_selftext_matching`: 验证 selftext 字段匹配
     - `test_filter_empty_aliases`: 验证空别名列表处理
     - `test_filter_config_fallback`: 验证配置加载失败时的降级行为
     - `test_regex_caching`: 验证正则表达式缓存机制

### 向后兼容性

- `_filter_posts_by_asset()` 函数签名不变
- 配置文件缺失时自动降级，不影响现有功能
- 对于配置文件中不存在的 ticker，使用 ticker 本身作为唯一别名

### 未来扩展

1. **动态配置更新**
   - 当前使用 `@lru_cache`，配置在进程生命周期内固定
   - 未来可添加 `_reload_ticker_aliases()` 函数清除缓存

2. **别名优先级与置信度**
   - 当前所有别名权重相同
   - 未来可添加两层别名系统：
     - **高置信度**（当前）：ticker、公司名、曾用名
     - **中置信度**（未来）：CEO 名字、主要产品名
   - 配置格式：`{"aliases": [{"text": "Jensen", "confidence": 0.7}]}`
   - 允许根据置信度阈值过滤

3. **加密货币特殊模式**
   - 支持 Unicode 符号：₿ (Bitcoin), Ξ (Ethereum)
   - 支持无词边界格式：hodlbtc, btcmaxi
   - 配置格式：`{"patterns": ["\u20bf", "btc"]}`

4. **匹配统计与调试**
   - 在 `meta` 中添加 `matched_by_alias` 字段
   - 记录每篇帖子是通过哪个别名匹配的
   - 用于分析别名效果和优化配置

5. **配置文件路径可配置**
   - 通过环境变量 `TICKER_ALIASES_PATH` 覆盖默认路径
   - 便于不同环境使用不同配置

## 测试策略

### 单元测试

1. **别名加载测试**
   - 验证配置文件正确加载
   - 验证缓存机制生效

2. **正则匹配测试**
   - Ticker 精确匹配（NVDA）
   - 公司名匹配（Nvidia）
   - Cashtag 匹配（$NVDA）
   - 词边界验证（NVDA vs NVDAX）
   - 大小写不敏感（nvidia, NVIDIA）

3. **降级行为测试**
   - 配置文件缺失时的回退逻辑
   - 配置文件格式错误时的回退逻辑

### 集成测试

1. **端到端测试**
   - Mock Reddit API，验证完整过滤管道
   - 验证 `meta` 中的统计字段正确性

2. **真实数据测试**
   - 使用真实 ticker（如 "NVDA"）调用 `get_reddit_discussion()`
   - 人工验证返回内容的相关性

## 风险与缓解

**风险 1**: 别名配置不完整
- **影响**: 某些常见变体无法匹配，召回率下降
- **缓解**:
  - 初始配置覆盖 Magnificent Seven 的核心别名
  - 通过真实数据测试验证召回率
  - 文档中说明如何添加新别名

**风险 2**: 正则表达式性能问题
- **影响**: 如果别名列表过长，正则匹配可能变慢
- **缓解**:
  - 当前 9 个资产，性能完全可控
  - 如果未来扩展，可引入预编译缓存

**风险 3**: 词边界在特殊字符场景下失效
- **影响**: 某些 Unicode 字符或标点符号可能影响词边界识别
- **缓解**:
  - Reddit 主要使用英文和 ASCII 标点，风险较低
  - 如果发现问题，可调整正则表达式

## 总结

本设计通过引入别名字典和正则词边界匹配，显著提升了 Reddit 文本过滤的精确度和召回率。核心改进包括：

1. **精确匹配**: 词边界正则消除误匹配（NVDA vs NVDAX）
2. **高召回率**: 支持 ticker、公司名、曾用名等常见别名
3. **Reddit 友好**: 兼容 Cashtag 格式（$NVDA）
4. **易维护**: 配置与代码分离，支持快速更新
5. **高性能**: 对于当前规模，匹配延迟 < 1ms

实现方案保持向后兼容，风险可控，预期能够为下游的情绪分析提供更高质量的输入数据。
