# 加密货币历史数据下载 - 快速开始

## 问题修复

已修复的问题：
1. ✅ 日期溢出问题（pandas Timestamp 转换错误）
2. ✅ 未来月份数据问题（自动限制到当前月份）
3. ✅ 批量插入性能优化
4. ✅ 数据量优化（只下载常用时间间隔）

## 立即开始

```bash
# 下载历史数据（约 5-10 分钟）
uv run python scripts/download_binance_vision.py
```

## 下载内容

- **币种**: BTC-USDT, ETH-USDT
- **时间间隔**: 15m, 1h, 4h, 1d, 1w, 1M
- **时间范围**: 2020-01 到 2026-03（当前月份）
- **预计数据量**: 约 50 MB，~480,000 条记录

## 下载后验证

```bash
# 查看数据统计
uv run python -c "
from app.database.crypto_ohlc import get_crypto_metadata

for symbol in ['BTC-USDT', 'ETH-USDT']:
    for bar in ['15m', '1H', '4H', '1D', '1W', '1M']:
        meta = get_crypto_metadata(symbol, bar)
        if meta:
            print(f'{symbol} {bar}: {meta[\"total_records\"]:>6,} records ({meta[\"data_start\"][:10]} to {meta[\"data_end\"][:10]})')
"
```

## 前端访问

下载完成后，前端可以通过以下 API 访问 K 线数据：

```
GET /api/stocks/BTC-USDT/ohlc?start=2024-01-01&end=2024-12-31&interval=1d
GET /api/stocks/ETH-USDT/ohlc?start=2024-01-01&end=2024-12-31&interval=1h
```

支持的 interval 参数：
- `15m` - 15 分钟
- `1h` - 1 小时
- `4h` - 4 小时
- `1d` 或 `day` - 日线
- `1w` 或 `week` - 周线
- `1m` 或 `month` - 月线

## 故障排查

### 如果下载中断

脚本使用 `ON CONFLICT` 处理重复数据，可以安全地重新运行：

```bash
uv run python scripts/download_binance_vision.py
```

### 如果需要重新下载

```bash
# 清理所有数据
uv run python scripts/clean_crypto_data.py --force

# 重新下载
uv run python scripts/download_binance_vision.py
```

### 如果前端显示 404

检查数据是否存在：

```bash
uv run python -c "
from app.database.crypto_ohlc import get_crypto_ohlc
data = get_crypto_ohlc('BTC-USDT', '1D', '2024-01-01', '2024-12-31')
print(f'Found {len(data)} records')
if data:
    print(f'First: {data[0][\"date\"][:10]}')
    print(f'Last: {data[-1][\"date\"][:10]}')
"
```

## 性能优化

脚本已包含以下优化：
- 批量插入（每批 10,000 条）
- 单事务提交
- 进度条显示
- 自动跳过无效数据

预计性能：
- 下载速度：~2-3 月/秒
- 插入速度：~10,000-50,000 条/秒
- 总时间：5-10 分钟
