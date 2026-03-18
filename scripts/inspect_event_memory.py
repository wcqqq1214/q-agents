from __future__ import annotations

import os
import sys

from langchain_chroma import Chroma


DEFAULT_PERSIST_DIR = "./chroma_event_db_stocks"
# Note: Use GOOGL not GOOG in database
DEFAULT_COLLECTION_NAME = "event_memory"


def main() -> None:
    """Inspect a few documents from the event memory Chroma DB.

    Usage:
        uv run python tests/inspect_event_memory.py
        uv run python tests/inspect_event_memory.py NVDA
        uv run python tests/inspect_event_memory.py ./chroma_event_db_stocks NVDA

    Env overrides:
        PERSIST_DIR: override persist directory
        COLLECTION_NAME: override collection name
    """

    persist_dir: str
    ticker: str | None

    if len(sys.argv) >= 3:
        persist_dir = sys.argv[1].strip()
        ticker = sys.argv[2].strip().upper()
    elif len(sys.argv) == 2:
        persist_dir = os.getenv("PERSIST_DIR", "") or DEFAULT_PERSIST_DIR
        ticker = sys.argv[1].strip().upper()
    else:
        persist_dir = os.getenv("PERSIST_DIR", "") or DEFAULT_PERSIST_DIR
        ticker = None

    collection_name = os.getenv("COLLECTION_NAME", DEFAULT_COLLECTION_NAME)

    db = Chroma(
        persist_directory=persist_dir,
        collection_name=collection_name,
    )

    # Show basic stats
    try:
        count = db._collection.count()  # type: ignore[attr-defined]
    except Exception:
        count = None
    print(f"Persist directory: {persist_dir}")
    print(f"Collection name: {collection_name}")
    if count is not None:
        print(f"Total documents in collection: {count}")

    # Fetch a small sample of documents, optionally filtered by ticker.
    if ticker:
        print(f"\nFiltering by ticker={ticker!r}")
        data = db.get(where={"ticker": ticker}, limit=5)
    else:
        print("\nNo ticker provided; sampling without ticker filter.")
        data = db.get(limit=5)

    ids = data.get("ids", [])
    docs = data.get("documents", [])
    metas = data.get("metadatas", [])

    print(f"\nSample size returned: {len(ids)}")
    for i, (id_, doc, meta) in enumerate(zip(ids, docs, metas), start=1):
        print("=" * 80)
        print(f"[{i}] id={id_}")
        print(f"metadata={meta}")
        print("content preview:")
        preview = (doc or "")[:600]
        print(preview)
        if len(doc or "") > 600:
            print("... [truncated]")


if __name__ == "__main__":
    main()


