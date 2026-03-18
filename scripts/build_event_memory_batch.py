"""Build event memory from existing Polygon database.

This script reads from finance_data.db (Phase 1-2 output) and builds
the Chroma vector database for RAG retrieval.

Usage:
    uv run python scripts/build_event_memory_batch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_conn
from app.rag.build_event_memory import create_memory_document, init_chroma_db

PERSIST_DIR = "./chroma_event_db_stocks"
TICKERS = ["NVDA", "MSFT", "TSLA", "AAPL", "GOOGL", "META", "AMZN"]


def build_memory_from_database() -> None:
    """Build event memory from existing database."""
    conn = get_conn()

    # Query relevant news with returns (allow T+5 to be NULL for recent events)
    query = """
    SELECT
        l1.news_id, l1.symbol, l1.key_discussion, l1.sentiment,
        n.title, n.description, n.article_url, n.publisher,
        na.trade_date, na.ret_t1, na.ret_t5
    FROM layer1_results l1
    JOIN news n ON l1.news_id = n.id
    JOIN news_aligned na ON l1.news_id = na.news_id AND l1.symbol = na.symbol
    WHERE l1.relevance = 'relevant'
      AND na.ret_t1 IS NOT NULL
      AND l1.symbol IN ({})
    ORDER BY l1.symbol, na.trade_date
    """.format(','.join('?' * len(TICKERS)))

    cursor = conn.cursor()
    cursor.execute(query, TICKERS)
    rows = cursor.fetchall()
    conn.close()

    print(f"Found {len(rows)} relevant events with returns")

    if not rows:
        print("No data to process")
        return

    # Build memory documents
    docs = []
    metadatas = []

    for row in rows:
        ticker = row['symbol']
        date = row['trade_date']

        # Build news summary from key_discussion and description
        key_disc = row['key_discussion'] or ''
        desc = row['description'] or ''
        title = row['title'] or ''

        news_summary = f"{title} — {key_disc}"
        if desc and desc not in news_summary:
            news_summary += f" {desc[:200]}"

        # Create memory document (T+5 may be None for recent events)
        returns = {
            "t1_return": row['ret_t1'],
            "t5_return": row['ret_t5'] if row['ret_t5'] is not None else 0.0,
        }

        doc = create_memory_document(
            ticker=ticker,
            date=date,
            news_summary=news_summary,
            returns=returns,
        )

        # Append source info
        doc += "\n数据来源：该事件由基于 Polygon.io 的新闻检索与 Layer1 语义分析自动挖掘，"
        doc += "并通过真实交易日对齐计算 T+1/T+5 收益率；仅供研究参考，不构成投资建议。\n"
        doc += f"代表性新闻标题：{title}\n"
        doc += f"新闻链接：{row['article_url']}\n"
        doc += f"发布者：{row['publisher']}\n"

        metadata = {
            "ticker": ticker,
            "date": date,
            "event_type": "news",
            "source_url": row['article_url'],
            "source_title": title,
            "publisher": row['publisher'],
            "sentiment": row['sentiment'] or 'neutral',
        }

        docs.append(doc)
        metadatas.append(metadata)

    print(f"Building Chroma database with {len(docs)} documents...")

    # Store in Chroma
    init_chroma_db(
        docs=docs,
        metadatas=metadatas,
        persist_directory=PERSIST_DIR,
    )

    print(f"✓ Complete: {len(docs)} events stored in {PERSIST_DIR}")

    # Print summary by ticker
    from collections import Counter
    ticker_counts = Counter(m['ticker'] for m in metadatas)
    print("\nEvents per ticker:")
    for ticker in TICKERS:
        count = ticker_counts.get(ticker, 0)
        print(f"  {ticker}: {count}")


def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("Building Event Memory from Polygon Database")
    print("=" * 60)
    print(f"Source: data/finance_data.db")
    print(f"Output: {PERSIST_DIR}")
    print(f"Tickers: {', '.join(TICKERS)}")
    print("=" * 60)
    print()

    build_memory_from_database()


if __name__ == "__main__":
    main()
