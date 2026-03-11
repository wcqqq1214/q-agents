from __future__ import annotations

from pathlib import Path
from pprint import pprint
import sys
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.tools.finance_tools import search_news_with_duckduckgo


def main() -> None:
    """Manual test script for the DuckDuckGo news search tool.

    This script runs a few sample queries and prints the structured results
    so you can visually inspect that titles, URLs, sources, and snippets
    look reasonable.
    """

    queries: List[str] = ["AAPL stock news", "MSFT earnings", "US inflation data"]

    for q in queries:
        print(f"=== Query: {q!r} ===")
        results = search_news_with_duckduckgo.invoke({"query": q, "limit": 3})
        pprint(results)
        print()


if __name__ == "__main__":
    main()

