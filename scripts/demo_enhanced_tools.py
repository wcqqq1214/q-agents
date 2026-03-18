"""Test script for enhanced quantitative tools."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.enhanced_tools import (
    get_stock_data_with_sentiment,
    search_news_with_returns,
)


def test_stock_data_with_sentiment():
    """Test get_stock_data_with_sentiment tool."""
    print("=" * 60)
    print("Testing get_stock_data_with_sentiment")
    print("=" * 60)

    result = get_stock_data_with_sentiment.invoke({"ticker": "NVDA", "days": 60})
    data = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
    else:
        print(f"✓ Ticker: {data['ticker']}")
        print(f"✓ Last date: {data['last_date']}")
        print(f"✓ Last close: ${data['last_close']:.2f}")
        print(f"\nTechnical Indicators:")
        print(f"  RSI(14): {data['rsi_14']:.2f}")
        print(f"  Volatility(5d): {data['volatility_5d']:.4f}")
        print(f"\nSentiment Features:")
        print(f"  Sentiment(3d): {data['sentiment_score_3d']:.3f}")
        print(f"  Sentiment(10d): {data['sentiment_score_10d']:.3f}")
        print(f"  Momentum: {data['sentiment_momentum_3d']:.3f}")
        print(f"\nNews Activity:")
        print(f"  Articles(3d): {data['news_count_3d']}")
        print(f"  Positive ratio: {data['positive_ratio_3d']:.2%}")
        print(f"  Negative ratio: {data['negative_ratio_3d']:.2%}")

    print()


def test_news_with_returns():
    """Test search_news_with_returns tool."""
    print("=" * 60)
    print("Testing search_news_with_returns")
    print("=" * 60)

    result = search_news_with_returns.invoke({
        "ticker": "TSLA",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "limit": 5,
    })
    data = json.loads(result)

    if "error" in data:
        print(f"❌ Error: {data['error']}")
    else:
        print(f"✓ Ticker: {data['ticker']}")
        print(f"✓ Date range: {data['start_date']} to {data['end_date']}")
        print(f"✓ Found {data['count']} articles with forward returns")
        print()

        for i, article in enumerate(data["articles"][:3], 1):
            print(f"  [{i}] {article['trade_date']}")
            print(f"      {article['title']}")
            print(f"      Sentiment: {article['sentiment']}")
            if article['key_discussion']:
                print(f"      Summary: {article['key_discussion']}")
            print(f"      Returns: T+1={article['ret_t1']}%, T+3={article['ret_t3']}%, T+5={article['ret_t5']}%")
            print()

    print()


if __name__ == "__main__":
    print("\n🧪 Testing Enhanced Quantitative Tools\n")

    test_stock_data_with_sentiment()
    test_news_with_returns()

    print("=" * 60)
    print("Tests complete!")
    print("=" * 60)
