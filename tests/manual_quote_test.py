from __future__ import annotations

from pprint import pprint
from pathlib import Path
import sys
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.tools.finance_tools import get_us_stock_quote


def main() -> None:
    """Manual test script for get_us_stock_quote tool.

    This script exercises the quote tool with a few example tickers and prints
    the structured results so you can visually inspect that the fields look
    reasonable and that error handling behaves as expected.
    """

    tickers: List[str] = ["AAPL", "MSFT", "INVALID123"]

    for symbol in tickers:
        print(f"=== {symbol} ===")
        result = get_us_stock_quote.invoke({"ticker": symbol})
        pprint(result)
        print()


if __name__ == "__main__":
    main()

