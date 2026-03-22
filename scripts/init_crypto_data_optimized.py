"""Optimized crypto K-line data initialization with resume support.

Features:
1. Resume from last successful download (断点续传)
2. Batch database commits with WAL mode (批量提交优化)
3. Progress tracking and error recovery
4. Disk space validation

Usage:
    uv run python scripts/init_crypto_data_optimized.py
"""

import asyncio
import sys
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Set, Tuple

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.batch_downloader_raw import download_daily_data_raw
from app.database.schema import init_db, get_conn
from app.database.batch_operations import BatchInserter


def enable_wal_mode():
    """Enable WAL mode for better write performance."""
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
    conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")   # Use memory for temp tables
    conn.close()
    print("✓ 启用 WAL 模式和性能优化")


def check_disk_space(required_gb: float = 2.0):
    """Check if there's enough disk space."""
    import shutil
    stats = shutil.disk_usage(Path.home())
    available_gb = stats.free / (1024**3)

    print(f"\n磁盘空间检查:")
    print(f"  可用空间: {available_gb:.1f} GB")
    print(f"  预计需要: {required_gb:.1f} GB")

    if available_gb < required_gb:
        print(f"  ✗ 磁盘空间不足！")
        return False
    else:
        print(f"  ✓ 磁盘空间充足")
        return True


def get_downloaded_dates(symbol: str, interval: str) -> Set[date]:
    """Get set of dates that have already been downloaded."""
    conn = get_conn()

    # Query distinct dates for this symbol and interval
    query = """
        SELECT DISTINCT DATE(date) as download_date
        FROM crypto_ohlc
        WHERE symbol = ? AND bar = ?
    """

    cursor = conn.execute(query, (symbol, interval))
    dates = {
        date.fromisoformat(row[0])
        for row in cursor.fetchall()
    }
    conn.close()

    return dates


def get_resume_point(start_date: date, end_date: date) -> Tuple[date, int]:
    """
    Determine where to resume downloading.

    Returns:
        (resume_date, already_downloaded_count)
    """
    symbols = ["BTCUSDT", "ETHUSDT"]
    intervals = ["1m", "1d"]

    # Find the earliest date that needs downloading
    all_downloaded = set()
    for symbol in symbols:
        for interval in intervals:
            downloaded = get_downloaded_dates(symbol, interval)
            if not all_downloaded:
                all_downloaded = downloaded
            else:
                all_downloaded &= downloaded  # Intersection

    if not all_downloaded:
        return start_date, 0

    # Find gaps in downloaded dates
    current = start_date
    while current <= end_date:
        if current not in all_downloaded:
            break
        current += timedelta(days=1)

    already_downloaded = len([d for d in all_downloaded if start_date <= d <= end_date])

    return current, already_downloaded


async def main():
    """Download data from 2020-01-01 to yesterday with resume support."""
    print("="*70)
    print("加密货币 K 线数据初始化（优化版）")
    print("="*70)

    # 1. Check disk space
    if not check_disk_space(required_gb=2.0):
        print("\n请清理磁盘空间后重试")
        return

    # 2. Initialize database
    print("\n初始化数据库...")
    init_db()
    print("✓ 数据库已初始化")

    # 3. Enable WAL mode for performance
    enable_wal_mode()

    # 4. Configuration
    symbols = ["BTCUSDT", "ETHUSDT"]
    intervals = ["1m", "1d"]
    start_date = date(2020, 1, 1)
    end_date = date.today() - timedelta(days=1)
    total_days = (end_date - start_date).days + 1

    # 5. Check for resume point
    print("\n检查断点续传...")
    resume_date, already_downloaded = get_resume_point(start_date, end_date)

    if already_downloaded > 0:
        print(f"✓ 发现已下载数据: {already_downloaded} 天")
        print(f"✓ 从 {resume_date} 继续下载")
    else:
        print(f"✓ 从头开始下载")
        resume_date = start_date

    remaining_days = (end_date - resume_date).days + 1

    print(f"\n下载配置:")
    print(f"  时间范围: {start_date} 至 {end_date}")
    print(f"  总天数: {total_days} 天")
    print(f"  已完成: {already_downloaded} 天")
    print(f"  剩余: {remaining_days} 天")
    print(f"  预计文件: ~{remaining_days * 4} 个")
    print(f"  预计记录: ~{remaining_days * 2882:,} 条\n")

    # 6. Download data with batch inserter
    total_records = 0
    success_count = 0
    fail_count = 0

    print("开始下载...")
    with BatchInserter(batch_size=5000) as inserter:
        current_date = resume_date
        while current_date <= end_date:
            # Progress indicator every 50 days
            days_done = (current_date - resume_date).days
            if days_done % 50 == 0 and days_done > 0:
                progress = (days_done / remaining_days) * 100
                print(f"\n进度: {progress:.1f}% - 日期: {current_date} - 成功: {success_count} - 失败: {fail_count}")

            day_records = 0
            day_success = True

            for symbol in symbols:
                for interval in intervals:
                    try:
                        records = await download_daily_data_raw(symbol, interval, current_date)
                        if records:
                            inserter.add_records(symbol, interval, records)
                            day_records += len(records)
                        else:
                            day_success = False
                    except Exception as e:
                        day_success = False
                        # Log error but continue

            total_records += day_records
            if day_success:
                success_count += 1
            else:
                fail_count += 1

            current_date += timedelta(days=1)

    # 7. Final summary
    print(f"\n\n{'='*70}")
    print(f"下载完成！")
    print(f"{'='*70}")
    print(f"本次下载:")
    print(f"  成功: {success_count:,} 天")
    print(f"  失败: {fail_count:,} 天")
    print(f"  新增记录: {total_records:,} 条")
    print(f"\n总计:")
    print(f"  已下载: {already_downloaded + success_count:,} 天")
    print(f"  数据范围: {start_date} 至 {end_date}")

    # 8. Database statistics
    conn = get_conn()
    cursor = conn.execute("SELECT COUNT(*) FROM crypto_ohlc")
    total_db_records = cursor.fetchone()[0]

    cursor = conn.execute("SELECT page_count * page_size / 1024.0 / 1024.0 FROM pragma_page_count(), pragma_page_size()")
    db_size_mb = cursor.fetchone()[0]

    conn.close()

    print(f"\n数据库统计:")
    print(f"  总记录数: {total_db_records:,}")
    print(f"  数据库大小: {db_size_mb:.1f} MB")

    print(f"\n提示：")
    print("- 如果中途中断，重新运行此脚本会自动从断点继续")
    print("- 失败的日期通常是因为 Binance Vision 尚未发布数据")
    print("- WAL 模式已启用，写入性能已优化")


if __name__ == "__main__":
    asyncio.run(main())
