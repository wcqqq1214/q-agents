from __future__ import annotations

import os
import sys

from langchain_chroma import Chroma


DEFAULT_PERSIST_DIR = "./chroma_event_db_stocks"
DEFAULT_COLLECTION_NAME = "event_memory"


def main() -> None:
    """List all distinct tickers stored in a Chroma collection.

    Usage:
        uv run python tests/list_tickers.py
        uv run python tests/list_tickers.py ./chroma_event_db_stocks

    Env overrides:
        PERSIST_DIR: override persist directory
        COLLECTION_NAME: override collection name
    """

    persist_dir = (
        (sys.argv[1].strip() if len(sys.argv) > 1 else "")
        or os.getenv("PERSIST_DIR", "")
        or DEFAULT_PERSIST_DIR
    )
    collection_name = os.getenv("COLLECTION_NAME", DEFAULT_COLLECTION_NAME)

    db = Chroma(
        persist_directory=persist_dir,
        collection_name=collection_name,
    )

    data = db.get(include=["metadatas"])
    metas = data.get("metadatas") or []

    tickers: set[str] = set()
    for meta in metas:
        if not meta:
            continue
        ticker = meta.get("ticker")
        if ticker:
            tickers.add(str(ticker).upper())

    tickers_list = sorted(tickers)
    print(f"Persist directory: {persist_dir}")
    print(f"Collection name: {collection_name}")
    print(f"Total distinct tickers: {len(tickers_list)}")
    for t in tickers_list:
        print(t)


if __name__ == "__main__":
    main()

