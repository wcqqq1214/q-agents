"""Export events from Chroma database to a text file.

Usage:
    # Export all events
    uv run python scripts/export_events.py

    # Export latest 100 events (sorted by date)
    uv run python scripts/export_events.py --latest 100

    # Export events for specific ticker
    uv run python scripts/export_events.py --ticker NVDA

    # Combine filters
    uv run python scripts/export_events.py --ticker NVDA --latest 50 --output nvda_latest.txt
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_chroma import Chroma
from app.embedding_config import create_embeddings

PERSIST_DIR = "./chroma_event_db_stocks"


def export_events(output_file="events.txt", ticker=None, limit=None, latest=False):
    """Export events to text file.

    Args:
        output_file: Output file path
        ticker: Filter by ticker symbol
        limit: Maximum number of events to export
        latest: If True, sort by date descending (newest first)
    """
    embeddings = create_embeddings()
    db = Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name="event_memory",
    )

    # Get events
    where = {"ticker": ticker} if ticker else None
    results = db.get(where=where, limit=limit or 50000)

    events = list(zip(results['ids'], results['documents'], results['metadatas']))

    # Sort by date if latest mode
    if latest:
        events = sorted(events, key=lambda x: x[2]['date'], reverse=True)
        if limit:
            events = events[:limit]

    total = len(events)
    print(f"导出 {total} 个事件到 {output_file}...")

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        # Header
        title = "最新事件记忆数据库导出" if latest else "事件记忆数据库导出"
        f.write(f"{title}\n")
        f.write(f"=" * 80 + "\n")
        f.write(f"导出事件数: {total}\n")
        if ticker:
            f.write(f"股票代码: {ticker}\n")
        if latest:
            f.write(f"按日期降序排列（最新在前）\n")
        f.write(f"=" * 80 + "\n\n")

        # Events
        for i, (doc_id, doc, meta) in enumerate(events, 1):
            f.write(f"\n{'=' * 80}\n")
            f.write(f"事件 #{i}\n")
            f.write(f"{'=' * 80}\n")
            f.write(f"股票: {meta['ticker']}\n")
            f.write(f"日期: {meta['date']}\n")
            f.write(f"情绪: {meta.get('sentiment', 'N/A')}\n")
            f.write(f"标题: {meta['source_title']}\n")
            f.write(f"链接: {meta['source_url']}\n")
            f.write(f"发布者: {meta.get('publisher', 'N/A')}\n")
            f.write(f"\n完整内容:\n")
            f.write(f"{'-' * 80}\n")
            f.write(doc)
            f.write(f"\n{'-' * 80}\n")

    print(f"✓ 导出完成: {output_file}")
    print(f"  总事件数: {total}")
    if latest and total > 0:
        print(f"  日期范围: {events[-1][2]['date']} 到 {events[0][2]['date']}")


def main():
    parser = argparse.ArgumentParser(description="Export events from Chroma database")
    parser.add_argument("--output", default="events.txt", help="Output file path")
    parser.add_argument("--ticker", help="Filter by ticker (e.g., NVDA)")
    parser.add_argument("--limit", type=int, help="Maximum number of events to export")
    parser.add_argument("--latest", type=int, metavar="N",
                        help="Export N latest events sorted by date (newest first)")

    args = parser.parse_args()

    # If --latest is specified, use it as limit and enable sorting
    if args.latest:
        limit = args.latest
        latest = True
        # Default output filename for latest mode
        if args.output == "events.txt":
            args.output = "latest_events.txt"
    else:
        limit = args.limit
        latest = False

    export_events(
        output_file=args.output,
        ticker=args.ticker,
        limit=limit,
        latest=latest,
    )


if __name__ == "__main__":
    main()
