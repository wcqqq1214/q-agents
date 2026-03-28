"""Clean old crypto OHLC data from database.

This script removes old data downloaded from OKX API to prepare for
Binance Vision data import.

Usage:
    uv run python scripts/clean_crypto_data.py [--force]
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

from app.database.schema import get_conn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_crypto_data(force=False):
    """Remove all crypto OHLC data and metadata."""
    conn = get_conn()

    try:
        # Check current data
        cursor = conn.execute("SELECT COUNT(*) FROM crypto_ohlc")
        count = cursor.fetchone()[0]
        logger.info(f"Current records in crypto_ohlc: {count:,}")

        cursor = conn.execute("SELECT symbol, bar, total_records FROM crypto_metadata")
        metadata = cursor.fetchall()
        logger.info(f"Current metadata entries: {len(metadata)}")
        for row in metadata:
            logger.info(f"  {row[0]} {row[1]}: {row[2]:,} records")

        if count == 0:
            logger.info("No data to clean.")
            return

        # Confirm deletion
        if not force:
            response = input("\nDelete all crypto data? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Cancelled.")
                return

        # Delete data
        logger.info("Deleting data...")
        conn.execute("DELETE FROM crypto_ohlc")
        conn.execute("DELETE FROM crypto_metadata")
        conn.commit()

        logger.info("✓ All crypto data deleted")

        # Verify
        cursor = conn.execute("SELECT COUNT(*) FROM crypto_ohlc")
        count = cursor.fetchone()[0]
        logger.info(f"Remaining records: {count}")

    finally:
        conn.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    clean_crypto_data(force=force)
