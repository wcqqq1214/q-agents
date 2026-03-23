"""统一的加密货币历史数据下载脚本

功能：
1. 下载月度数据（2020-01 到上个月）- 使用 Binance Vision 月度压缩包（更快）
2. 下载每日数据（本月1日到昨天）- 使用 Binance Vision 每日文件
3. 自动检测并填补数据gap
4. 支持断点续传
5. 批量插入优化
6. WAL 模式优化

用法：
    uv run python scripts/download_crypto_data.py
"""

import asyncio
import sys
import sqlite3
import zipfile
import io
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Set, Tuple, Optional
import pandas as pd
import requests
from tqdm import tqdm

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.batch_downloader_raw import download_daily_data_raw
from app.database.schema import init_db, get_conn
from app.database.batch_operations import BatchInserter
from app.database.crypto_ohlc import get_max_date

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Binance Vision configuration
BINANCE_VISION_MONTHLY_BASE = "https://data.binance.vision/data/spot/monthly/klines"
BINANCE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]


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


def download_monthly_kline(symbol: str, interval: str, year: int, month: int) -> Optional[pd.DataFrame]:
    """Download and parse a single monthly K-line file from Binance Vision."""
    month_str = str(month).zfill(2)
    file_name = f"{symbol}-{interval}-{year}-{month_str}.zip"
    url = f"{BINANCE_VISION_MONTHLY_BASE}/{symbol}/{interval}/{file_name}"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            logger.warning(f"下载失败 {file_name}: HTTP {response.status_code}")
            return None

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                df = pd.read_csv(f, names=BINANCE_COLUMNS)
                df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']].rename(columns={'open_time': 'timestamp'})
                return df

    except Exception as e:
        logger.error(f"处理文件出错 {file_name}: {e}")
        return None


def get_downloaded_months(symbol: str, interval: str) -> set:
    """Get set of (year, month) tuples that have already been downloaded."""
    conn = get_conn()
    query = """
        SELECT DISTINCT strftime('%Y', date) as year, strftime('%m', date) as month
        FROM crypto_ohlc
        WHERE symbol = ? AND bar = ?
    """
    cursor = conn.execute(query, (symbol, interval))
    months = {(int(row[0]), int(row[1])) for row in cursor.fetchall()}
    conn.close()
    return months


def download_monthly_data(symbol: str, interval: str, start_year: int, end_year: int, inserter) -> int:
    """Download monthly data for a symbol and interval."""
    db_symbol = f"{symbol[:3]}-{symbol[3:]}"  # BTCUSDT -> BTC-USDT
    downloaded_months = get_downloaded_months(db_symbol, interval)

    current_date = datetime.now()
    months_to_download = []

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if year == current_date.year and month >= current_date.month:
                break
            if (year, month) not in downloaded_months:
                months_to_download.append((year, month))

    if not months_to_download:
        logger.info(f"{symbol} {interval}: 所有月度数据已下载")
        return 0

    logger.info(f"{symbol} {interval}: 需要下载 {len(months_to_download)} 个月的数据")

    total_records = 0
    for year, month in tqdm(months_to_download, desc=f"{symbol} {interval} 月度"):
        df = download_monthly_kline(symbol, interval, year, month)

        if df is not None and not df.empty:
            records = []
            for _, row in df.iterrows():
                try:
                    dt = row['timestamp'].to_pydatetime()
                    timestamp_ms = int(dt.timestamp() * 1000)
                    records.append({
                        "timestamp": timestamp_ms,
                        "date": dt.isoformat(),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": float(row['volume'])
                    })
                except (ValueError, OverflowError):
                    continue

            if records:
                inserter.add_records(db_symbol, interval, records)
                total_records += len(records)

    return total_records


def detect_gaps(symbol: str, interval: str, start_date: date, end_date: date) -> list[Tuple[date, date]]:
    """Detect gaps in downloaded data.

    Args:
        symbol: Database symbol (e.g., 'BTC-USDT')
        interval: K-line interval (e.g., '1m', '1d')
        start_date: Start date to check
        end_date: End date to check

    Returns:
        List of (gap_start, gap_end) tuples
    """
    conn = get_conn()

    # Get all dates that have data
    query = """
        SELECT DISTINCT DATE(date) as download_date
        FROM crypto_ohlc
        WHERE symbol = ? AND bar = ?
        AND DATE(date) >= ? AND DATE(date) <= ?
        ORDER BY download_date
    """

    cursor = conn.execute(query, (symbol, interval, start_date.isoformat(), end_date.isoformat()))
    downloaded_dates = {date.fromisoformat(row[0]) for row in cursor.fetchall()}
    conn.close()

    # Find gaps
    gaps = []
    current = start_date
    gap_start = None

    while current <= end_date:
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


async def fill_gaps(symbols: list[str], intervals: list[str], inserter) -> int:
    """Fill gaps in data for all symbols and intervals.

    Args:
        symbols: List of trading symbols (e.g., ['BTCUSDT', 'ETHUSDT'])
        intervals: List of intervals (e.g., ['1m', '1d'])
        inserter: BatchInserter instance

    Returns:
        Total number of days filled
    """
    print("\n" + "="*70)
    print("阶段 3: 检测并填补数据gap")
    print("="*70)

    start_date = date(2020, 1, 1)
    yesterday = date.today() - timedelta(days=1)

    total_filled = 0

    for symbol in symbols:
        db_symbol = f"{symbol[:3]}-{symbol[3:]}"  # BTCUSDT -> BTC-USDT

        for interval in intervals:
            # Detect gaps
            gaps = detect_gaps(db_symbol, interval, start_date, yesterday)

            if not gaps:
                logger.info(f"{symbol} {interval}: 无gap，数据连续")
                continue

            logger.info(f"{symbol} {interval}: 发现 {len(gaps)} 个gap")

            # Fill each gap
            for gap_start, gap_end in gaps:
                gap_days = (gap_end - gap_start).days + 1
                logger.info(f"  填补gap: {gap_start} 至 {gap_end} ({gap_days} 天)")

                current = gap_start
                success = 0
                fail = 0

                while current <= gap_end:
                    try:
                        records = await download_daily_data_raw(symbol, interval, current)
                        if records:
                            inserter.add_records(db_symbol, interval, records)
                            success += 1
                        else:
                            fail += 1
                    except Exception as e:
                        logger.error(f"    下载失败 {current}: {e}")
                        fail += 1

                    current += timedelta(days=1)

                logger.info(f"  完成: 成功 {success} 天, 失败 {fail} 天")
                total_filled += success

    return total_filled


async def main():
    """Download data from 2020-01-01 to yesterday with monthly + daily strategy."""
    print("="*70)
    print("加密货币 K 线数据下载（月度+每日混合策略）")
    print("="*70)

    # 1. Check disk space
    if not check_disk_space(required_gb=5.0):
        print("\n请清理磁盘空间后重试")
        return

    # 2. Initialize database
    print("\n初始化数据库...")
    init_db()
    print("✓ 数据库已初始化")

    # 3. Enable WAL mode for performance
    enable_wal_mode()

    # 4. Configuration
    symbols = ["BTCUSDT", "ETHUSDT"]  # BTC和ETH
    intervals = ["1m", "1d"]  # 1分钟和1天数据
    start_year = 2020
    current_date = datetime.now()

    print(f"\n下载配置:")
    print(f"  币种: {', '.join(symbols)}")
    print(f"  时间粒度: {', '.join(intervals)}")
    print(f"  时间范围: {start_year}-01-01 至 {current_date.date()}")
    print(f"  策略: 月度压缩包（历史月份）+ 每日文件（当前月份）\n")

    total_monthly_records = 0
    total_daily_records = 0
    total_gap_filled = 0

    with BatchInserter(batch_size=10000) as inserter:
        # ===== 阶段 1: 下载月度数据（2020-01 到上个月）=====
        print("="*70)
        print("阶段 1: 下载月度数据（更快，适合历史数据）")
        print("="*70)

        for symbol in symbols:
            for interval in intervals:
                records = download_monthly_data(
                    symbol=symbol,
                    interval=interval,
                    start_year=start_year,
                    end_year=current_date.year,
                    inserter=inserter
                )
                total_monthly_records += records
                print(f"✓ {symbol} {interval}: 月度数据 {records:,} 条")

        # ===== 阶段 2: 下载每日数据（本月1日到昨天）=====
        print("\n" + "="*70)
        print("阶段 2: 下载每日数据（当前月份）")
        print("="*70)

        # 计算当前月份的日期范围
        first_day_of_month = date(current_date.year, current_date.month, 1)
        yesterday = date.today() - timedelta(days=1)

        if first_day_of_month <= yesterday:
            print(f"下载范围: {first_day_of_month} 至 {yesterday}")

            current = first_day_of_month
            success_count = 0
            fail_count = 0

            while current <= yesterday:
                day_records = 0
                day_success = True

                for symbol in symbols:
                    for interval in intervals:
                        try:
                            records = await download_daily_data_raw(symbol, interval, current)
                            if records:
                                db_symbol = f"{symbol[:3]}-{symbol[3:]}"
                                inserter.add_records(db_symbol, interval, records)
                                day_records += len(records)
                            else:
                                day_success = False
                        except Exception as e:
                            logger.error(f"下载失败 {symbol} {interval} {current}: {e}")
                            day_success = False

                total_daily_records += day_records
                if day_success:
                    success_count += 1
                else:
                    fail_count += 1

                current += timedelta(days=1)

            print(f"✓ 每日数据: 成功 {success_count} 天, 失败 {fail_count} 天, 记录 {total_daily_records:,} 条")
        else:
            print("当前月份暂无数据需要下载")

        # ===== 阶段 3: 检测并填补gap =====
        total_gap_filled = await fill_gaps(symbols, intervals, inserter)

    # ===== 最终统计 =====
    print(f"\n\n{'='*70}")
    print(f"下载完成！")
    print(f"{'='*70}")
    print(f"本次下载:")
    print(f"  月度数据: {total_monthly_records:,} 条")
    print(f"  每日数据: {total_daily_records:,} 条")
    print(f"  填补gap: {total_gap_filled} 天")
    print(f"  总计: {total_monthly_records + total_daily_records:,} 条")

    # Database statistics
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
    print("- 月度数据下载速度更快，适合历史数据")
    print("- 每日数据用于补充当前月份")
    print("- 自动检测并填补数据gap")
    print("- 重新运行此脚本会自动跳过已下载的月份")
    print("- WAL 模式已启用，写入性能已优化")


if __name__ == "__main__":
    asyncio.run(main())
