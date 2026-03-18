"""探索 Polymarket 市场的工具脚本"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.polymarket.client import PolymarketClient
import json


def explore_markets(limit=20):
    """探索当前活跃的市场"""
    client = PolymarketClient()

    print("=" * 70)
    print("探索 Polymarket 活跃市场")
    print("=" * 70)

    markets = client.fetch_markets(limit=limit, closed=False, active=True)

    print(f"\n找到 {len(markets)} 个活跃市场\n")

    # 按分类统计
    categories = {}
    tags_set = set()

    for market in markets:
        # 分类统计
        category = market.get('category') or 'uncategorized'
        categories[category] = categories.get(category, 0) + 1

        # 收集标签
        events = market.get('events', [])
        if events and len(events) > 0:
            event = events[0]
            # 注意：API 可能没有直接的 tags 字段，我们从其他字段推断

    print("市场分类统计:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    print("\n" + "=" * 70)
    print("市场列表（按交易量排序）:")
    print("=" * 70)

    # 按交易量排序
    markets_sorted = sorted(
        markets,
        key=lambda m: float(m.get('volume24hr', 0) or 0),
        reverse=True
    )

    for i, market in enumerate(markets_sorted[:15], 1):
        question = market.get('question', 'N/A')
        volume_24h = float(market.get('volume24hr', 0) or 0)
        category = market.get('category') or 'N/A'

        # 解析概率
        outcome_prices = market.get('outcomePrices', '[]')
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)
        prob_yes = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0

        print(f"\n{i}. {question[:65]}")
        print(f"   分类: {category}")
        print(f"   概率: {prob_yes:.1%} Yes")
        print(f"   24h交易量: ${volume_24h:,.0f}")


def search_by_keyword(keyword, limit=10):
    """按关键词搜索市场"""
    client = PolymarketClient()

    print("\n" + "=" * 70)
    print(f"搜索关键词: '{keyword}'")
    print("=" * 70)

    markets = client.search_markets(keyword, limit=limit)

    if not markets:
        print(f"\n未找到包含 '{keyword}' 的市场")
        return

    print(f"\n找到 {len(markets)} 个相关市场:\n")

    for i, market in enumerate(markets, 1):
        parsed = client.parse_market_data(market)
        print(f"{i}. {parsed['question'][:65]}")
        print(f"   概率: {parsed['probability_yes']:.1%} Yes / {parsed['probability_no']:.1%} No")
        print(f"   24h交易量: ${parsed['volume_24h']:,.0f}")
        print(f"   分类: {parsed['category'] or 'N/A'}")
        print()


def search_multiple_keywords(keywords):
    """搜索多个关键词"""
    print("\n" + "=" * 70)
    print("批量搜索测试")
    print("=" * 70)

    for keyword in keywords:
        client = PolymarketClient()
        markets = client.search_markets(keyword, limit=3)
        print(f"\n'{keyword}': 找到 {len(markets)} 个市场")
        if markets:
            print(f"  最相关: {markets[0].get('question', 'N/A')[:60]}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='探索 Polymarket 市场')
    parser.add_argument('--explore', action='store_true', help='探索活跃市场')
    parser.add_argument('--search', type=str, help='搜索关键词')
    parser.add_argument('--batch', nargs='+', help='批量搜索多个关键词')
    parser.add_argument('--limit', type=int, default=20, help='返回结果数量')

    args = parser.parse_args()

    if args.explore:
        explore_markets(limit=args.limit)
    elif args.search:
        search_by_keyword(args.search, limit=args.limit)
    elif args.batch:
        search_multiple_keywords(args.batch)
    else:
        # 默认：显示热门市场和测试几个搜索
        explore_markets(limit=15)

        print("\n\n")
        test_keywords = ['Bitcoin', 'Trump', 'AI', 'economy', 'stock', 'tech', 'crypto']
        search_multiple_keywords(test_keywords)
