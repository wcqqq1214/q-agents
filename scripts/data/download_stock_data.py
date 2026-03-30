"""统一的股票历史数据下载脚本（使用 yfinance）

功能：
1. 下载年度数据（2020 到去年）- 按年分批下载
2. 下载本年数据（今年1月1日到昨天）- 按月分批下载
3. 自动检测并填补数据gap
4. 支持断点续传
5. 批量插入优化
6. WAL 模式优化
7. 自动处理速率限制（添加延迟）

用法：
    uv run python scripts/download_stock_data.py
"""

import asyncio
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Set, Tuple

import yfinance as yf

# Add project root to Python path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from app.database.schema import get_conn, init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Stock symbols to download
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def enable_wal_mode():
    """Enable WAL mode for better write performance."""
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.close()
    print("✓ 启用 WAL 模式和性能优化")


def check_disk_space(required_gb: float = 1.0):
    """Check if there's enough disk space."""
    import shutil

    stats = shutil.disk_usage(Path.home())
    available_gb = stats.free / (1024**3)

    print("\n磁盘空间检查:")
    print(f"  可用空间: {available_gb:.1f} GB")
    print(f"  预计需要: {required_gb:.1f} GB")

    if available_gb < required_gb:
        print("  ✗ 磁盘空间不足！")
        return False
    else:
        print("  ✓ 磁盘空间充足")
        return True


def get_downloaded_dates(symbol: str) -> Set[date]:
    """Get set of dates that have already been downloaded for a symbol."""
    conn = get_conn()
    query = """
        SELECT DISTINCT DATE(date) as download_date
        FROM ohlc
        WHERE symbol = ?
    """
    cursor = conn.execute(query, (symbol,))
    dates = {date.fromisoformat(row[0]) for row in cursor.fetchall()}
    conn.close()
    return dates


def download_year_data(symbol: str, year: int, conn) -> int:
    """Download data for a specific year using yfinance."""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    today = date.today()
    if date.fromisoformat(end_date) > today:
        end_date = today.isoformat()

    try:
        logger.info(f"  下载 {symbol} {year}...")

        # Download data using yfinance
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, auto_adjust=True)

        if df.empty:
            logger.warning(f"  {symbol} {year}: 无数据")
            return 0

        # Convert to records
        records = []
        for idx, row in df.iterrows():
            try:
                # Handle both Timestamp and DatetimeIndex
                if hasattr(idx, "strftime"):
                    date_str = idx.strftime("%Y-%m-%d")
                else:
                    date_str = str(idx)[:10]  # Extract YYYY-MM-DD from string

                records.append(
                    {
                        "date": date_str,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                )
            except (ValueError, KeyError) as e:
                logger.warning(f"  跳过无效数据: {idx}, {e}")
                continue

        if records:
            # Insert directly into ohlc table (no timestamp or bar columns)
            query = """
                INSERT OR REPLACE INTO ohlc (symbol, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            data = [
                (
                    symbol,
                    r["date"],
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["volume"],
                )
                for r in records
            ]
            conn.executemany(query, data)
            conn.commit()
            return len(records)

        return 0

    except Exception as e:
        logger.error(f"  下载失败 {symbol} {year}: {e}")
        return 0
    finally:
        # Add delay to avoid rate limiting
        time.sleep(1)


def detect_gaps(symbol: str, start_date: date, end_date: date) -> List[Tuple[date, date]]:
    """Detect gaps in downloaded data (excluding weekends)."""
    conn = get_conn()

    query = """
        SELECT DISTINCT DATE(date) as download_date
        FROM ohlc
        WHERE symbol = ?
        AND DATE(date) >= ? AND DATE(date) <= ?
        ORDER BY download_date
    """

    cursor = conn.execute(query, (symbol, start_date.isoformat(), end_date.isoformat()))
    downloaded_dates = {date.fromisoformat(row[0]) for row in cursor.fetchall()}
    conn.close()

    # Find gaps (skip weekends)
    gaps = []
    current = start_date
    gap_start = None

    while current <= end_date:
        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() < 5:
            if current not in downloaded_dates:
                if gap_start is None:
                    gap_start = current
            else:
                if gap_start is not None:
                    gaps.append((gap_start, current - timedelta(days=1)))
                    gap_start = None
        current += timedelta(days=1)

    # Handle gap at the end
    if gap_start is not None:
        gaps.append((gap_start, end_date))

    return gaps


def fill_gap(symbol: str, gap_start: date, gap_end: date, conn) -> int:
    """Fill a single gap in data using yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=gap_start.isoformat(), end=gap_end.isoformat(), auto_adjust=True)

        if df.empty:
            return 0

        records = []
        for idx, row in df.iterrows():
            try:
                # Handle both Timestamp and DatetimeIndex
                if hasattr(idx, "strftime"):
                    date_str = idx.strftime("%Y-%m-%d")
                else:
                    date_str = str(idx)[:10]  # Extract YYYY-MM-DD from string

                records.append(
                    {
                        "date": date_str,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                )
            except (ValueError, KeyError):
                continue

        if records:
            # Insert directly into ohlc table (no timestamp or bar columns)
            query = """
                INSERT OR REPLACE INTO ohlc (symbol, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            data = [
                (
                    symbol,
                    r["date"],
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["volume"],
                )
                for r in records
            ]
            conn.executemany(query, data)
            conn.commit()
            return len(records)

        return 0

    except Exception as e:
        logger.error(f"  填补gap失败 {symbol} {gap_start} to {gap_end}: {e}")
        return 0
    finally:
        time.sleep(1)


async def main():
    """Download stock data from 2020-01-01 to yesterday."""
    print("=" * 70)
    print("股票历史数据下载（使用 yfinance）")
    print("=" * 70)

    # 1. Check disk space
    if not check_disk_space(required_gb=1.0):
        print("\n请清理磁盘空间后重试")
        return

    # 2. Initialize database
    print("\n初始化数据库...")
    init_db()
    print("✓ 数据库已初始化")

    # 3. Enable WAL mode
    enable_wal_mode()

    # 4. Configuration
    start_year = 2020
    current_year = datetime.now().year
    yesterday = date.today() - timedelta(days=1)

    print("\n下载配置:")
    print(f"  股票代码: {', '.join(SYMBOLS)}")
    print(f"  时间范围: {start_year}-01-01 至 {yesterday}")
    print("  数据源: yfinance (免费，无限制)")
    print("  延迟策略: 每次请求后等待1秒\n")

    total_records = 0

    # Get database connection
    conn = get_conn()

    try:
        # ===== 阶段 1: 按年下载历史数据 =====
        print("=" * 70)
        print("阶段 1: 按年下载历史数据")
        print("=" * 70)

        for symbol in SYMBOLS:
            print(f"\n处理 {symbol}...")
            downloaded_dates = get_downloaded_dates(symbol)

            for year in range(start_year, current_year + 1):
                year_start = date(year, 1, 1)
                year_end = date(year, 12, 31) if year < current_year else yesterday

                # Count existing data
                year_dates = {d for d in downloaded_dates if year_start <= d <= year_end}
                expected_days = (year_end - year_start).days + 1

                if len(year_dates) > expected_days * 0.9:
                    logger.info(f"  {symbol} {year}: 已有 {len(year_dates)} 天数据，跳过")
                    continue

                records = download_year_data(symbol, year, conn)
                total_records += records
                logger.info(f"  ✓ {symbol} {year}: {records} 条记录")

        # ===== 阶段 2: 检测并填补gap =====
        print("\n" + "=" * 70)
        print("阶段 2: 检测并填补数据gap")
        print("=" * 70)

        gap_filled = 0
        for symbol in SYMBOLS:
            gaps = detect_gaps(symbol, date(start_year, 1, 1), yesterday)

            if not gaps:
                logger.info(f"{symbol}: 无gap，数据连续")
                continue

            logger.info(f"{symbol}: 发现 {len(gaps)} 个gap")

            for gap_start, gap_end in gaps:
                gap_days = (gap_end - gap_start).days + 1
                logger.info(f"  填补gap: {gap_start} 至 {gap_end} ({gap_days} 天)")

                records = fill_gap(symbol, gap_start, gap_end, conn)
                gap_filled += records
                if records > 0:
                    logger.info(f"  完成: {records} 条记录")
                else:
                    logger.info("  完成: 0 条记录（可能是节假日）")

        total_records += gap_filled
    finally:
        conn.close()

    # ===== 最终统计 =====
    print(f"\n\n{'=' * 70}")
    print("下载完成！")
    print(f"{'=' * 70}")
    print(f"本次下载: {total_records:,} 条记录")

    # Database statistics
    conn = get_conn()
    cursor = conn.execute("SELECT COUNT(*) FROM ohlc")
    total_db_records = cursor.fetchone()[0]

    cursor = conn.execute(
        "SELECT page_count * page_size / 1024.0 / 1024.0 FROM pragma_page_count(), pragma_page_size()"
    )
    db_size_mb = cursor.fetchone()[0]

    conn.close()

    print("\n数据库统计:")
    print(f"  总记录数: {total_db_records:,}")
    print(f"  数据库大小: {db_size_mb:.1f} MB")

    print("\n提示：")
    print("- 使用 yfinance 下载，免费无限制")
    print("- 自动跳过已下载的年份（90%阈值）")
    print("- 自动检测并填补数据gap")
    print("- 每次请求后等待1秒避免速率限制")
    print("- 重新运行此脚本会自动跳过已下载的数据")
    print("- WAL 模式已启用，写入性能已优化")


if __name__ == "__main__":
    asyncio.run(main())
