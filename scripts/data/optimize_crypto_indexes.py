"""Optimize crypto_ohlc table indexes for better query performance.

This script:
1. Drops old date-based indexes (not used by our queries)
2. Creates optimized timestamp-based indexes
3. Analyzes the table for query planner optimization

Usage:
    uv run python scripts/optimize_crypto_indexes.py
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def optimize_indexes():
    """Optimize crypto_ohlc table indexes."""
    db_path = "data/finance_data.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("优化 crypto_ohlc 表索引...\n")

    # 1. 检查现有索引
    print("1. 检查现有索引:")
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='crypto_ohlc'"
    )
    existing_indexes = cursor.fetchall()
    for idx_name, idx_sql in existing_indexes:
        if idx_sql:  # Skip auto-generated indexes
            print(f"   - {idx_name}")

    # 2. 删除旧的基于 date 的索引（我们使用 timestamp）
    print("\n2. 删除旧索引:")
    old_indexes = ["idx_crypto_ohlc_symbol_date", "idx_crypto_ohlc_symbol_bar_date"]
    for idx_name in old_indexes:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")
            print(f"   ✓ 删除 {idx_name}")
        except Exception as e:
            print(f"   ✗ 删除 {idx_name} 失败: {e}")

    # 3. 创建优化的索引
    print("\n3. 创建优化索引:")

    # 索引 1: (symbol, bar, timestamp) - 用于 API 查询
    # 这是最重要的索引，覆盖我们的主要查询模式
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crypto_symbol_bar_timestamp
            ON crypto_ohlc(symbol, bar, timestamp DESC)
        """)
        print("   ✓ idx_crypto_symbol_bar_timestamp (用于 API 查询)")
    except Exception as e:
        print(f"   ✗ 创建索引失败: {e}")

    # 索引 2: (symbol, bar) - 用于聚合查询
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crypto_symbol_bar
            ON crypto_ohlc(symbol, bar)
        """)
        print("   ✓ idx_crypto_symbol_bar (用于聚合查询)")
    except Exception as e:
        print(f"   ✗ 创建索引失败: {e}")

    # 4. 运行 ANALYZE 优化查询计划器
    print("\n4. 运行 ANALYZE 优化查询计划器...")
    try:
        cursor.execute("ANALYZE crypto_ohlc")
        print("   ✓ ANALYZE 完成")
    except Exception as e:
        print(f"   ✗ ANALYZE 失败: {e}")

    # 5. 提交更改
    conn.commit()

    # 6. 显示最终索引列表
    print("\n5. 最终索引列表:")
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='crypto_ohlc'"
    )
    final_indexes = cursor.fetchall()
    for idx_name, idx_sql in final_indexes:
        if idx_sql:
            print(f"   - {idx_name}")
            print(f"     {idx_sql}")

    # 7. 显示表统计信息
    print("\n6. 表统计信息:")
    cursor.execute("SELECT COUNT(*) FROM crypto_ohlc")
    total_rows = cursor.fetchone()[0]
    print(f"   总记录数: {total_rows:,}")

    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM crypto_ohlc")
    total_symbols = cursor.fetchone()[0]
    print(f"   币种数: {total_symbols}")

    cursor.execute("SELECT COUNT(DISTINCT bar) FROM crypto_ohlc")
    total_bars = cursor.fetchone()[0]
    print(f"   时间间隔数: {total_bars}")

    conn.close()
    print("\n✓ 索引优化完成！")


if __name__ == "__main__":
    optimize_indexes()
