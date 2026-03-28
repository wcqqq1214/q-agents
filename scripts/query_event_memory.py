"""Query event memory database with various filters.

Usage:
    uv run python scripts/query_event_memory.py --ticker NVDA --limit 10
    uv run python scripts/query_event_memory.py --sentiment positive
    uv run python scripts/query_event_memory.py --date-from 2024-01-01 --date-to 2024-12-31
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_chroma import Chroma

from app.embedding_config import create_embeddings

PERSIST_DIR = "./data/chroma_event_db_stocks"


def query_events(ticker=None, sentiment=None, date_from=None, date_to=None, limit=50):
    """Query events with filters."""
    embeddings = create_embeddings()
    db = Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name="event_memory",
    )

    # Build filter
    where = {}
    if ticker:
        where["ticker"] = ticker
    if sentiment:
        where["sentiment"] = sentiment

    # Get more results to filter by date
    if where:
        results = db.get(where=where, limit=limit * 10)
    else:
        results = db.get(limit=limit * 10)

    # Filter by date and collect matching events
    matching_events = []
    for doc_id, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
        # Filter by date if specified
        if date_from and meta["date"] < date_from:
            continue
        if date_to and meta["date"] > date_to:
            continue

        matching_events.append((doc_id, doc, meta))
        if len(matching_events) >= limit:
            break

    # Display results
    print(f"Found {len(matching_events)} events")
    print("=" * 80)

    for i, (doc_id, doc, meta) in enumerate(matching_events, 1):
        print(f"\n[{i}] {meta['ticker']} - {meta['date']}")
        print(f"Sentiment: {meta.get('sentiment', 'N/A')}")
        print(f"Title: {meta['source_title'][:80]}...")
        print(f"URL: {meta['source_url']}")
        print("\nContent preview:")
        print(doc[:400])
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Query event memory database")
    parser.add_argument("--ticker", help="Filter by ticker (e.g., NVDA)")
    parser.add_argument("--sentiment", help="Filter by sentiment (positive/negative/neutral)")
    parser.add_argument("--date-from", help="Filter from date (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="Filter to date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    query_events(
        ticker=args.ticker,
        sentiment=args.sentiment,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
