"""Batch processing script for Layer 1 semantic extraction using Anthropic Batch API.

This script submits large batches of news articles to Anthropic's Batch API for
cost-effective processing (50% discount). Use this for initial historical data
processing or large backfills.

Usage:
    python scripts/batch_submit.py [--symbol SYMBOL] [--limit LIMIT]
    python scripts/batch_collect.py <batch_id>

Batch API benefits:
- 50% cost reduction compared to real-time API
- No rate limits
- Ideal for processing thousands of historical articles
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from app.database import get_conn
from app.pipeline.layer1 import _build_batch_prompt, get_pending_articles

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
BATCH_SIZE = 50


def submit_batch_api(symbol: str, articles: List[Dict[str, Any]]) -> str:
    """Submit articles to Anthropic Batch API for async processing.

    Args:
        symbol: Stock ticker symbol.
        articles: List of article dictionaries.

    Returns:
        Batch ID for tracking.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: uv add anthropic")
        raise

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. This script requires Anthropic API for batch processing."
        )

    client = anthropic.Anthropic(api_key=api_key)

    requests = []
    for i in range(0, len(articles), BATCH_SIZE):
        chunk = articles[i : i + BATCH_SIZE]
        chunk_ids = "|".join(a["id"] for a in chunk)
        prompt = _build_batch_prompt(symbol, chunk)

        requests.append(
            {
                "custom_id": f"{symbol}|{i}|{chunk_ids}",
                "params": {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
            }
        )

    logger.info(f"Submitting {len(requests)} batch requests for {symbol}...")
    batch = client.messages.batches.create(requests=requests)

    # Store batch job in database
    conn = get_conn()
    conn.execute(
        """INSERT INTO batch_jobs (batch_id, symbol, status, total, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            batch.id,
            symbol,
            batch.processing_status,
            len(articles),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    logger.info(f"Batch submitted: {batch.id}")
    logger.info(f"Status: {batch.processing_status}")
    return batch.id


def check_batch_status(batch_id: str) -> Dict[str, Any]:
    """Check the status of a batch job.

    Args:
        batch_id: Batch ID to check.

    Returns:
        Dictionary with batch status information.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: uv add anthropic")
        raise

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=api_key)
    batch = client.messages.batches.retrieve(batch_id)

    # Update database
    conn = get_conn()
    conn.execute(
        "UPDATE batch_jobs SET status = ? WHERE batch_id = ?",
        (batch.processing_status, batch_id),
    )
    conn.commit()
    conn.close()

    return {
        "batch_id": batch.id,
        "status": batch.processing_status,
        "request_counts": {
            "processing": batch.request_counts.processing,
            "succeeded": batch.request_counts.succeeded,
            "errored": batch.request_counts.errored,
            "canceled": batch.request_counts.canceled,
            "expired": batch.request_counts.expired,
        },
    }


def collect_batch_results(batch_id: str) -> Dict[str, int]:
    """Collect results from a completed batch API job.

    Args:
        batch_id: Batch ID to collect results from.

    Returns:
        Dictionary with collection statistics.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: uv add anthropic")
        raise

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=api_key)
    conn = get_conn()

    stats = {"processed": 0, "relevant": 0, "irrelevant": 0, "errors": 0}

    logger.info(f"Collecting results for batch {batch_id}...")

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        parts = custom_id.split("|", 2)
        if len(parts) < 3:
            stats["errors"] += 1
            continue

        symbol = parts[0]
        article_ids = parts[2].split("|")

        if result.result.type != "succeeded":
            stats["errors"] += len(article_ids)
            continue

        message = result.result.message
        text = message.content[0].text if message.content else "[]"

        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                stats["errors"] += len(article_ids)
                continue

            items = json.loads(text[start:end])

            for item in items:
                idx = item.get("i")
                if idx is None or idx >= len(article_ids):
                    stats["errors"] += 1
                    continue

                is_relevant = item.get("r") in ("y", "relevant")
                relevance = "relevant" if is_relevant else "irrelevant"
                raw_s = item.get("s", "0")
                sentiment = {"+": "positive", "-": "negative"}.get(raw_s, "neutral")

                conn.execute(
                    """INSERT OR REPLACE INTO layer1_results
                       (news_id, symbol, relevance, key_discussion, sentiment,
                        reason_growth, reason_decrease)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        article_ids[idx],
                        symbol,
                        relevance,
                        item.get("e", ""),
                        sentiment,
                        item.get("u", ""),
                        item.get("d", ""),
                    ),
                )
                stats["processed"] += 1
                if is_relevant:
                    stats["relevant"] += 1
                else:
                    stats["irrelevant"] += 1

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse batch result: {e}")
            stats["errors"] += len(article_ids)

    conn.execute(
        "UPDATE batch_jobs SET status = 'collected', finished_at = ? WHERE batch_id = ?",
        (datetime.now().isoformat(), batch_id),
    )
    conn.commit()
    conn.close()

    logger.info(
        f"Collection complete: {stats['processed']} processed, {stats['relevant']} relevant"
    )
    return stats


def main_submit():
    """Main entry point for batch submission."""
    parser = argparse.ArgumentParser(
        description="Submit Layer 1 batch processing jobs to Anthropic Batch API"
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

    logger.info("=" * 60)
    logger.info("Batch API Submission - Layer 1 Semantic Extraction")
    logger.info("=" * 60)
    logger.info(f"Tickers: {', '.join(symbols)}")
    logger.info(f"Max articles per ticker: {args.limit}")
    logger.info("Cost: ~50% cheaper than real-time API")
    logger.info("=" * 60)
    logger.info("")

    batch_ids = []

    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{len(symbols)}] Processing {symbol}...")

        try:
            articles = get_pending_articles(symbol, limit=args.limit)

            if not articles:
                logger.info(f"  No pending articles for {symbol}")
                continue

            logger.info(f"  Found {len(articles)} pending articles")
            batch_id = submit_batch_api(symbol, articles)
            batch_ids.append((symbol, batch_id))

        except Exception as exc:
            logger.error(f"Failed to submit batch for {symbol}: {exc}", exc_info=True)

        logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("BATCH SUBMISSION COMPLETE")
    logger.info(f"Submitted {len(batch_ids)} batch jobs")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    for symbol, batch_id in batch_ids:
        logger.info(f"  {symbol}: python scripts/batch_collect.py {batch_id}")
    logger.info("")
    logger.info("Check status:")
    logger.info("  python scripts/batch_status.py <batch_id>")


def main_collect():
    """Main entry point for batch collection."""
    parser = argparse.ArgumentParser(description="Collect results from Anthropic Batch API")
    parser.add_argument(
        "batch_id",
        type=str,
        help="Batch ID to collect results from",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Batch API Collection")
    logger.info("=" * 60)
    logger.info(f"Batch ID: {args.batch_id}")
    logger.info("=" * 60)
    logger.info("")

    try:
        # Check status first
        status = check_batch_status(args.batch_id)
        logger.info(f"Status: {status['status']}")
        logger.info(f"Succeeded: {status['request_counts']['succeeded']}")
        logger.info(f"Errored: {status['request_counts']['errored']}")
        logger.info("")

        if status["status"] != "ended":
            logger.warning(f"Batch is not complete yet (status: {status['status']})")
            logger.info("Wait for batch to complete before collecting results.")
            return

        # Collect results
        stats = collect_batch_results(args.batch_id)

        logger.info("=" * 60)
        logger.info("COLLECTION COMPLETE")
        logger.info(f"Processed: {stats['processed']}")
        logger.info(f"Relevant: {stats['relevant']}")
        logger.info(f"Errors: {stats['errors']}")
        logger.info("=" * 60)

    except Exception as exc:
        logger.error(f"Failed to collect batch results: {exc}", exc_info=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        sys.argv.pop(1)  # Remove 'collect' from args
        main_collect()
    else:
        main_submit()
