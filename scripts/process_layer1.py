"""Process Layer 1 semantic extraction for all tickers.

This script runs Layer 1 (LLM semantic extraction) on all pending news articles.
It processes 50 articles per API call for efficiency.

Usage:
    python scripts/process_layer1.py [--symbol SYMBOL] [--limit LIMIT]

    --symbol: Process only this ticker (default: all Magnificent Seven)
    --limit: Maximum articles to process per ticker (default: 10000)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from app.pipeline import run_layer1

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Magnificent Seven tickers
MAGNIFICENT_SEVEN = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]


def main() -> None:
    """Main entry point for Layer 1 processing."""
    parser = argparse.ArgumentParser(
        description="Run Layer 1 semantic extraction on pending news articles"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        help="Process only this ticker (default: all Magnificent Seven)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum articles to process per ticker (default: 10000)",
    )
    args = parser.parse_args()

    symbols = [args.symbol.upper()] if args.symbol else MAGNIFICENT_SEVEN

    logger.info("="*60)
    logger.info("Layer 1 Semantic Extraction")
    logger.info("="*60)
    logger.info(f"Tickers: {', '.join(symbols)}")
    logger.info(f"Max articles per ticker: {args.limit}")
    logger.info("="*60)
    logger.info("")

    total_processed = 0
    total_relevant = 0
    total_api_calls = 0
    total_retries = 0

    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{len(symbols)}] Processing {symbol}...")

        try:
            result = run_layer1(symbol, max_articles=args.limit)

            if result.get("status") == "no_pending":
                logger.info(f"  No pending articles for {symbol}")
            else:
                total_processed += result["processed"]
                total_relevant += result["relevant"]
                total_api_calls += result["api_calls"]
                total_retries += result.get("retries", 0)

                logger.info(f"  Processed: {result['processed']}/{result['total']}")
                logger.info(f"  Relevant: {result['relevant']}")
                logger.info(f"  API calls: {result['api_calls']}")
                if result.get("retries", 0) > 0:
                    logger.info(f"  Retries: {result['retries']}")

        except Exception as exc:
            logger.error(f"Failed to process {symbol}: {exc}", exc_info=True)

        logger.info("")

    # Summary
    logger.info("="*60)
    logger.info("LAYER 1 COMPLETE")
    logger.info(f"Total processed: {total_processed}")
    logger.info(f"Total relevant: {total_relevant}")
    logger.info(f"Total API calls: {total_api_calls}")
    if total_retries > 0:
        logger.info(f"Total retries: {total_retries}")
    logger.info("="*60)


if __name__ == "__main__":
    main()
