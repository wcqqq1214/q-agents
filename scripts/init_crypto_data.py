"""Initialize crypto K-line data for cold-hot architecture.

This script downloads historical data from 2021-03-22 to 2026-03-21
to populate the cold storage layer.

Usage:
    uv run python scripts/init_crypto_data.py
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.batch_downloader import download_daily_data
from app.database.schema import init_db


async def main():
    """Download data from 2017-08-17 (Binance launch) to yesterday for BTCUSDT and ETHUSDT."""
    print("初始化加密货币 K 线数据...")

    # Initialize database
    init_db()
    print("✓ 数据库已初始化")

    symbols = ["BTCUSDT", "ETHUSDT"]
    intervals = ["1m", "1d"]

    # Download from Binance launch date to yesterday
    # BTCUSDT and ETHUSDT both started on 2017-08-17
    start_date = date(2017, 8, 17)
    end_date = date.today() - timedelta(days=1)  # Yesterday

    total_days = (end_date - start_date).days + 1
    print(f"\n下载时间范围: {start_date} 至 {end_date}")
    print(f"总共 {total_days} 天的数据")
    print(f"预计下载: ~{total_days * 2 * 2:,} 个文件 (2个币种 × 2个时间间隔)\n")

    total_records = 0
    success_count = 0
    fail_count = 0

    current_date = start_date
    while current_date <= end_date:
        # 每100天显示一次进度
        if (current_date - start_date).days % 100 == 0:
            progress = ((current_date - start_date).days / total_days) * 100
            print(f"\n进度: {progress:.1f}% - 日期: {current_date}")

        day_records = 0
        day_success = True
        for symbol in symbols:
            for interval in intervals:
                try:
                    records = await download_daily_data(symbol, interval, current_date)
                    if records:
                        day_records += len(records)
                    else:
                        day_success = False
                except Exception:
                    day_success = False

        total_records += day_records
        if day_success:
            success_count += 1
        else:
            fail_count += 1

        current_date += timedelta(days=1)

    print(f"\n\n{'='*60}")
    print(f"下载完成！")
    print(f"{'='*60}")
    print(f"成功: {success_count:,} 天")
    print(f"失败: {fail_count:,} 天")
    print(f"共下载: {total_records:,} 条记录")
    print(f"\n数据时间范围: {start_date} 至 {end_date}")
    print(f"\n提示：")
    print("- 1m 数据：每天1440条记录（24小时 × 60分钟）")
    print("- 1d 数据：每天1条记录")
    print("- 失败的日期通常是因为 Binance Vision 尚未发布数据")


if __name__ == "__main__":
    asyncio.run(main())
