"""One-off script to backfill the 2026-03-20 to 2026-03-23 stock data gap."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.ohlc import get_ohlc, update_metadata, upsert_ohlc_overwrite
from app.services.stock_updater import SYMBOLS, fetch_recent_ohlc


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    logger.info("=" * 70)
    logger.info("开始补数据：2026-03-20 到 2026-03-23")
    logger.info("=" * 70)

    logger.info("Fetching last 10 days of data to cover gap period...")
    data_by_symbol = fetch_recent_ohlc(SYMBOLS, days=10)

    if not data_by_symbol:
        logger.error("未获取到数据，终止补数据")
        return 1

    success_count = 0
    total_records = 0

    for symbol, records in data_by_symbol.items():
        try:
            if records:
                upsert_ohlc_overwrite(symbol, records)
                dates = [r["date"] for r in records]
                update_metadata(symbol, min(dates), max(dates))
                total_records += len(records)
                success_count += 1
                logger.info(f"✓ {symbol}: {len(records)} 条记录已补充")
        except Exception as exc:
            logger.error(f"❌ {symbol} 补数据失败: {exc}")

    logger.info("=" * 70)
    logger.info(f"补数据完成: {success_count}/{len(SYMBOLS)} 只股票")
    logger.info(f"Total records processed: {total_records}")
    logger.info("=" * 70)

    logger.info("验证 Gap 是否已填补...")
    for symbol in SYMBOLS:
        try:
            records = get_ohlc(symbol, "2026-03-20", "2026-03-23")
            logger.info(f"{symbol}: {len(records)} 条记录在 Gap 期间")
        except Exception as exc:
            logger.error(f"Failed to verify {symbol}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
