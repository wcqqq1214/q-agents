# Fix Stock Updater Single Symbol Bug Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 stock_updater.py 中 `_extract_symbol_frame` 函数无法正确处理单个股票下载的 bug，使 stocks k-line 数据能够正常更新到最新

**Architecture:** 改进 `_extract_symbol_frame` 函数，正确处理 yfinance 在单个股票和多个股票下载时返回的不同 MultiIndex 列格式

**Tech Stack:** Python, pandas, yfinance

**Spec Document:** 问题诊断显示 yfinance 单个股票下载返回 `('Close', 'AAPL')` 格式的 MultiIndex，而多个股票返回 `('AAPL', 'Close')` 格式，当前代码无法处理前者

---

## File Structure

**Modified Files:**
- `app/services/stock_updater.py:48-58` - 修复 `_extract_symbol_frame` 函数

**No New Files**

---

## Task 1: 修复 `_extract_symbol_frame` 函数

**Files:**
- Modify: `app/services/stock_updater.py:48-58`

- [ ] **Step 1: 编写测试验证当前 bug**

创建临时测试脚本验证问题：

Run: `uv run python -c "from app.services.stock_updater import fetch_recent_ohlc; data = fetch_recent_ohlc(['AAPL'], days=2); print(f'Records: {len(data.get(\"AAPL\", []))}')"`

Expected: 输出 "Records: 0" 或错误信息，确认 bug 存在

- [ ] **Step 2: 修复 `_extract_symbol_frame` 函数**

在 `app/services/stock_updater.py` 中，将第 48-58 行的函数替换为：

```python
def _extract_symbol_frame(data: pd.DataFrame, symbol: str, symbols_count: int) -> pd.DataFrame:
    """Extract data for a single symbol from yfinance download result."""

    # Single symbol case
    if symbols_count == 1:
        if isinstance(data.columns, pd.MultiIndex):
            # yfinance returns MultiIndex columns for single symbol
            # Format: ('Close', 'AAPL'), ('High', 'AAPL'), etc.
            # Check if symbol is in level 1 (single symbol format)
            if symbol in data.columns.get_level_values(1):
                # Drop the symbol level, keep only price types (Open, High, Low, Close, Volume)
                return data.droplevel(1, axis=1)
        # If not MultiIndex or symbol not in level 1, return as-is
        # (handles edge case of simple Index with ['Open', 'High', 'Low', 'Close', 'Volume'])
        return data

    # Multiple symbols case
    if isinstance(data.columns, pd.MultiIndex):
        # Check level 0 first (standard multi-symbol format)
        if symbol in data.columns.get_level_values(0):
            return data[symbol]
        # Fallback to level -1
        if symbol in data.columns.get_level_values(-1):
            return data.xs(symbol, axis=1, level=-1)

    return data
```

- [ ] **Step 3: 测试单个股票下载**

Run: `uv run python -c "from app.services.stock_updater import fetch_recent_ohlc; data = fetch_recent_ohlc(['AAPL'], days=2); records = data.get('AAPL', []); print(f'Records: {len(records)}'); [print(f\"  {r['date']}: \${r['close']:.2f}\") for r in records]"`

Expected: 输出 "Records: 2" 并显示两天的数据和价格

- [ ] **Step 4: 测试多个股票下载**

Run: `uv run python -c "from app.services.stock_updater import fetch_recent_ohlc; data = fetch_recent_ohlc(['AAPL', 'MSFT'], days=2); print(f'AAPL: {len(data.get(\"AAPL\", []))} records'); print(f'MSFT: {len(data.get(\"MSFT\", []))} records')"`

Expected: 输出 "AAPL: 2 records" 和 "MSFT: 2 records"

- [ ] **Step 5: 测试完整的 7 个股票批量下载**

Run: `uv run python -c "from app.services.stock_updater import fetch_recent_ohlc, SYMBOLS; data = fetch_recent_ohlc(SYMBOLS, days=2); print(f'Success: {len(data)}/{len(SYMBOLS)} symbols'); [print(f'{s}: {len(data.get(s, []))} records') for s in SYMBOLS]"`

Expected: 输出 "Success: 7/7 symbols" 并显示每个股票都有 2 条记录

- [ ] **Step 6: Commit**

```bash
git add app/services/stock_updater.py
git commit -m "fix: handle yfinance single-symbol MultiIndex format

_extract_symbol_frame now correctly handles both single and multi-symbol
column formats, fixing stock data update failures"
```

---

## Task 2: 手动触发更新验证修复

**Files:**
- None (verification only)

- [ ] **Step 1: 手动触发一次完整更新**

Run: `uv run python -c "from app.services.stock_updater import update_stocks_intraday_sync; update_stocks_intraday_sync()"`

Expected: 看到更新日志，显示 7 个股票都成功更新，并显示最新价格

- [ ] **Step 2: 验证数据库中有最新数据**

Run: `uv run python -c "from app.database.ohlc import get_ohlc; from datetime import date; today = date.today().isoformat(); records = get_ohlc('AAPL', today, today); print(f'AAPL {today}: {len(records)} records'); [print(f\"  Close: \${r['close']:.2f}\") for r in records]"`

Expected: 输出 "AAPL <today's date>: 1 records" 并显示今天的收盘价（如果在交易时段运行）

- [ ] **Step 3: 验证所有 7 个股票都有最新数据**

Run: `uv run python -c "from app.database.ohlc import get_ohlc; from app.services.stock_updater import SYMBOLS; from datetime import date; today = date.today().isoformat(); [print(f'{s}: {len(get_ohlc(s, today, today))} records') for s in SYMBOLS]"`

Expected: 每个股票都显示 "1 records"（如果在交易时段运行）

- [ ] **Step 4: 检查 FastAPI 应用日志**

Run: `tail -n 50 /proc/$(pgrep -f 'uvicorn app.api.main:app')/fd/1 2>/dev/null || echo "Check application logs manually"`

Expected: 如果应用在运行，应该能看到调度器的更新日志

- [ ] **Step 5: 重启 FastAPI 应用（如果需要）**

如果应用正在运行且使用了 `--reload` 模式，代码会自动重新加载。

如果没有使用 `--reload` 模式，需要手动重启：

```bash
# 停止当前进程
pkill -f "uvicorn app.api.main:app"

# 在新的终端窗口中启动应用
# uv run uvicorn app.api.main:app --host 0.0.0.0 --port 8080 --reload
```

Expected: 应用重启，调度器开始正常工作

注意：请在单独的终端窗口中运行 uvicorn 命令，不要使用后台进程

---

## Success Criteria

✅ **单个股票下载正常**
- `fetch_recent_ohlc(['AAPL'], days=2)` 返回 2 条记录

✅ **多个股票下载正常**
- `fetch_recent_ohlc(['AAPL', 'MSFT'], days=2)` 两个股票都返回 2 条记录

✅ **7 个股票批量下载正常**
- `fetch_recent_ohlc(SYMBOLS, days=2)` 所有 7 个股票都返回 2 条记录

✅ **数据库有最新数据**
- 所有 7 个股票在数据库中都有当天的数据

✅ **调度器正常工作**
- FastAPI 应用运行时，每 15 分钟自动更新一次

---

## Rollback Plan

如果修复出现问题：

```bash
# 回滚到修复前
git log --oneline -5
git revert <commit-hash>
```

---

## Notes

- 这是一个 bug 修复，不是新功能
- 修复后，现有的调度器会自动开始正常工作
- 无需修改数据库结构或其他代码
- 修复向后兼容，不影响现有功能
