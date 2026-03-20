---
name: Chart Time Granularity Redesign
description: Change K-line chart from time-span view to time-granularity view with aggregated OHLC data
type: feature
---

# K线图时间粒度重构设计文档

## 1. 概述

### 1.1 目标
将K线图的时间维度从"时间跨度"模式改为"时间粒度"模式：
- **当前**: 按钮显示 1M/3M/6M/1Y/5Y，每根K线代表1天，显示该时间跨度内的所有日K线
- **目标**: 按钮显示 D/W/M/Y，每根K线代表对应的时间粒度（1天/1周/1月/1年），显示聚合后的OHLC数据

### 1.2 用户价值
- 更灵活的时间维度分析：用户可以快速切换不同粒度查看价格走势
- 更清晰的长期趋势：周线/月线/年线能更好地展示长期趋势，减少噪音
- 保持交互性：用户仍可通过鼠标滚轮缩放和拖拽查看更多历史数据

## 2. 详细设计

### 2.1 类型定义变更

**frontend/src/lib/types.ts**
```typescript
// 修改前
export type TimeRange = '1M' | '3M' | '6M' | '1Y' | '5Y';

// 修改后
export type TimeRange = 'D' | 'W' | 'M' | 'Y';
```

### 2.2 后端 API 设计

#### 2.2.1 API 端点
```
GET /stocks/{symbol}/ohlc
```

#### 2.2.2 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 股票代码（路径参数） |
| `start` | string | 否 | 5年前 | 开始日期 (YYYY-MM-DD) |
| `end` | string | 否 | 今天 | 结束日期 (YYYY-MM-DD) |
| `interval` | string | 否 | `day` | 时间粒度: `day`, `week`, `month`, `year` |

#### 2.2.3 响应格式
```json
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2024-01-01",
      "open": 150.0,
      "high": 155.0,
      "low": 148.0,
      "close": 153.0,
      "volume": 50000000
    }
  ]
}
```

#### 2.2.4 聚合逻辑

**Week (周线)**
- 分组: 按 ISO 周（周一到周日）
- `open`: 该周第一个交易日的开盘价
- `high`: 该周内的最高价
- `low`: 该周内的最低价
- `close`: 该周最后一个交易日的收盘价
- `volume`: 该周总成交量
- `date`: 该周的周一日期

**Month (月线)**
- 分组: 按自然月
- `open`: 该月第一个交易日的开盘价
- `high`: 该月内的最高价
- `low`: 该月内的最低价
- `close`: 该月最后一个交易日的收盘价
- `volume`: 该月总成交量
- `date`: 该月第一天日期 (YYYY-MM-01)

**Year (年线)**
- 分组: 按自然年
- `open`: 该年第一个交易日的开盘价
- `high`: 该年内的最高价
- `low`: 该年内的最低价
- `close`: 该年最后一个交易日的收盘价
- `volume`: 该年总成交量
- `date`: 该年第一天日期 (YYYY-01-01)

### 2.3 后端实现

#### 2.3.1 数据库查询函数

**app/database/ohlc.py** - 新增函数

```python
def get_ohlc_aggregated(symbol: str, start: str, end: str, interval: str) -> List[Dict]:
    """Query aggregated OHLC data from database.

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format
        interval: Time granularity ('day', 'week', 'month', 'year')

    Returns:
        List of aggregated OHLC records as dictionaries
    """
    from app.database.schema import get_conn
    conn = get_conn()

    if interval == 'day':
        # 直接返回每日数据，无需聚合
        query = """
            SELECT date, open, high, low, close, volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)

    elif interval == 'week':
        # 按 ISO 周聚合（周一到周日）
        query = """
            SELECT
                date(date, 'weekday 0', '-6 days') as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND date(o2.date, 'weekday 0', '-6 days') = date(ohlc.date, 'weekday 0', '-6 days')
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND date(o3.date, 'weekday 0', '-6 days') = date(ohlc.date, 'weekday 0', '-6 days')
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY date(date, 'weekday 0', '-6 days')
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)

    elif interval == 'month':
        # 按月聚合
        query = """
            SELECT
                strftime('%Y-%m-01', date) as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND strftime('%Y-%m', o2.date) = strftime('%Y-%m', ohlc.date)
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND strftime('%Y-%m', o3.date) = strftime('%Y-%m', ohlc.date)
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY strftime('%Y-%m', date)
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)

    elif interval == 'year':
        # 按年聚合
        query = """
            SELECT
                strftime('%Y-01-01', date) as date,
                (SELECT open FROM ohlc o2
                 WHERE o2.symbol = ohlc.symbol
                 AND strftime('%Y', o2.date) = strftime('%Y', ohlc.date)
                 ORDER BY o2.date ASC LIMIT 1) as open,
                MAX(high) as high,
                MIN(low) as low,
                (SELECT close FROM ohlc o3
                 WHERE o3.symbol = ohlc.symbol
                 AND strftime('%Y', o3.date) = strftime('%Y', ohlc.date)
                 ORDER BY o3.date DESC LIMIT 1) as close,
                SUM(volume) as volume
            FROM ohlc
            WHERE symbol = ? AND date >= ? AND date <= ?
            GROUP BY strftime('%Y', date)
            ORDER BY date ASC
        """
        params = (symbol.upper(), start, end)

    else:
        conn.close()
        raise ValueError(f"Invalid interval: {interval}")

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]
```

**app/database/__init__.py** - 导出新函数

需要在 `__all__` 列表中添加 `get_ohlc_aggregated`：

```python
__all__ = [
    "get_conn",
    "init_db",
    "DEFAULT_DB_PATH",
    "get_ohlc",
    "get_ohlc_aggregated",  # 新增
    "get_metadata",
    "upsert_ohlc",
    "update_metadata",
]
```

#### 2.3.2 API 路由修改

**app/api/routes/ohlc.py** - 修改现有端点

```python
@router.get("/{symbol}/ohlc", response_model=OHLCResponse)
def get_stock_ohlc(
    symbol: str,
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("day", description="Time granularity: day, week, month, year"),
):
    """Get OHLC data for a stock symbol with optional time aggregation."""
    # Validate interval
    valid_intervals = ["day", "week", "month", "year"]
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Must be one of: {', '.join(valid_intervals)}"
        )

    # Default to 5 years if not specified
    if not end:
        end = datetime.now().date().isoformat()
    if not start:
        start = (datetime.now().date() - timedelta(days=5*365)).isoformat()

    # Validate date range
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start date must be before end date")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    # Query database with aggregation
    try:
        data = get_ohlc_aggregated(symbol, start, end, interval)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLC data found for {symbol}"
            )

        return OHLCResponse(
            symbol=symbol.upper(),
            data=[OHLCRecord(**record) for record in data]
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch OHLC for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Database error")
```

### 2.4 前端实现

#### 2.4.1 类型定义

**frontend/src/lib/types.ts**

```typescript
// 修改 TimeRange 类型
export type TimeRange = 'D' | 'W' | 'M' | 'Y';
```

#### 2.4.2 TimeRangeSelector 组件

**frontend/src/components/chart/TimeRangeSelector.tsx**

```typescript
const TIME_RANGES: TimeRange[] = ['D', 'W', 'M', 'Y'];

export function TimeRangeSelector({ value, onChange, disabled }: TimeRangeSelectorProps) {
  const labels: Record<TimeRange, string> = {
    'D': 'Day',
    'W': 'Week',
    'M': 'Month',
    'Y': 'Year',
  };

  return (
    <div className="flex gap-1">
      {TIME_RANGES.map((range) => (
        <Button
          key={range}
          variant={value === range ? 'default' : 'outline'}
          size="sm"
          onClick={() => onChange(range)}
          disabled={disabled}
          className="min-w-[60px]"
        >
          {labels[range]}
        </Button>
      ))}
    </div>
  );
}
```

#### 2.4.3 KLineChart 组件

**frontend/src/components/chart/KLineChart.tsx**

主要修改点：

1. **时间窗口计算函数**

```typescript
function calculateDateRange(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();

  switch (range) {
    case 'D':
      // Day: 显示最近3个月的每日数据（约60-90根K线）
      start.setMonth(start.getMonth() - 3);
      break;
    case 'W':
      // Week: 显示最近1年的每周数据（约52根K线）
      start.setFullYear(start.getFullYear() - 1);
      break;
    case 'M':
      // Month: 显示最近3年的每月数据（约36根K线）
      start.setFullYear(start.getFullYear() - 3);
      break;
    case 'Y':
      // Year: 显示所有可用的年度数据（5年，约5根K线）
      start.setFullYear(start.getFullYear() - 5);
      break;
  }

  return {
    start: start.toISOString().split('T')[0],
    end: end.toISOString().split('T')[0],
  };
}
```

**说明**: 这些时间窗口是推荐的初始值，目的是让每个视图都有足够的数据点来观察趋势但不会太密集。这些值可以根据实际使用情况调整。

2. **API 调用修改**

```typescript
const fetchData = useCallback(async () => {
  if (!selectedStock) {
    setOhlcData([]);
    return;
  }

  setLoading(true);
  setError(null);

  try {
    const { start, end } = calculateDateRange(timeRange);

    // 映射前端 TimeRange 到后端 interval 参数
    const intervalMap: Record<TimeRange, string> = {
      'D': 'day',
      'W': 'week',
      'M': 'month',
      'Y': 'year',
    };

    const response = await api.getOHLC(
      selectedStock,
      start,
      end,
      intervalMap[timeRange]  // 新增 interval 参数
    );
    setOhlcData(response.data);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load chart data';
    setError(message);
    toast({
      title: 'Failed to load chart',
      description: 'Unable to fetch OHLC data',
      variant: 'destructive',
    });
  } finally {
    setLoading(false);
  }
}, [selectedStock, timeRange, toast]);
```

**说明**:
- 时间窗口（start/end）由前端根据 timeRange 计算
- API 总是获取完整的时间窗口数据
- lightweight-charts 的 `fitContent()` 方法会自动调整初始可见范围以显示所有数据
- 用户可以通过滚轮缩放和拖拽查看窗口内的所有数据
- **时区处理**: 所有日期使用 YYYY-MM-DD 格式，不包含时区信息。数据库中的日期基于市场交易日（美股为 EST/EDT），前端显示时不做时区转换

3. **默认值修改**

```typescript
// 将默认时间范围从 '3M' 改为 'W'
const [timeRange, setTimeRange] = useState<TimeRange>('W');
```

#### 2.4.4 API 客户端

**frontend/src/lib/api.ts**

```typescript
export const api = {
  // 修改 getOHLC 函数签名，增加 interval 参数
  async getOHLC(
    symbol: string,
    start: string,
    end: string,
    interval: string = 'day'  // 新增参数，默认值 'day'
  ): Promise<OHLCResponse> {
    const params = new URLSearchParams({
      start,
      end,
      interval,  // 传递 interval 参数
    });
    const response = await fetch(
      `${API_BASE_URL}/stocks/${symbol}/ohlc?${params}`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      }
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch OHLC data: ${response.statusText}`);
    }
    return response.json();
  },

  // ... 其他 API 方法保持不变
};
```

## 3. 实现步骤

### 3.1 后端实现
1. 在 `app/database/ohlc.py` 中添加 `get_ohlc_aggregated()` 函数
2. 在 `app/database/__init__.py` 中导出 `get_ohlc_aggregated`
3. 修改 `app/api/routes/ohlc.py` 中的 `get_stock_ohlc()` 端点
4. 编写单元测试验证聚合逻辑

### 3.2 前端实现
1. 修改 `frontend/src/lib/types.ts` 中的 `TimeRange` 类型
2. 更新 `frontend/src/components/chart/TimeRangeSelector.tsx` 组件
3. 修改 `frontend/src/components/chart/KLineChart.tsx` 组件
4. 更新 `frontend/src/lib/api.ts` 中的 API 调用

### 3.3 测试验证
1. 后端单元测试：验证各个 interval 的聚合逻辑
   - 测试边界情况：周/月/年边界的数据聚合
   - 测试数据缺失：周末、节假日等无交易日的处理
   - 测试 ISO 周边界：验证周一作为一周开始的正确性
   - **测试数据集**: 使用 AAPL 的5年历史数据（约1250条日线记录）
2. 前端集成测试：验证按钮切换和数据展示
3. 手动测试：验证图表交互（缩放、拖拽）
4. 性能测试：验证聚合查询响应时间
   - **性能要求**: 所有 interval 查询在5年数据集（AAPL，约1250条记录）上必须 < 500ms
   - 如果超过此阈值，需要优化 SQL（使用窗口函数或预聚合）

## 4. 向后兼容性

### 4.1 API 兼容性
- `interval` 参数为可选，默认值为 `day`
- **重要**: 现有调用方不传 `interval` 参数时，将继续接收每日数据，行为与之前完全一致
- 不影响其他可能调用此 API 的服务
- `/stocks/{symbol}/data-status` 端点无需修改，保持不变

### 4.2 前端兼容性
- 修改了 `TimeRange` 类型定义，需要全局搜索确保没有其他地方使用旧值
- `api.getOHLC()` 增加了可选参数，现有调用仍然有效

### 4.3 示例 API 响应

**Day interval (interval=day)**
```json
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2024-01-02",
      "open": 150.0,
      "high": 155.0,
      "low": 148.0,
      "close": 153.0,
      "volume": 50000000
    },
    {
      "date": "2024-01-03",
      "open": 153.0,
      "high": 157.0,
      "low": 152.0,
      "close": 156.0,
      "volume": 48000000
    }
  ]
}
```

**Week interval (interval=week)**
```json
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2024-01-01",
      "open": 150.0,
      "high": 160.0,
      "low": 148.0,
      "close": 158.0,
      "volume": 250000000
    },
    {
      "date": "2024-01-08",
      "open": 158.0,
      "high": 165.0,
      "low": 157.0,
      "close": 163.0,
      "volume": 240000000
    }
  ]
}
```

**Month interval (interval=month)**
```json
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2024-01-01",
      "open": 150.0,
      "high": 170.0,
      "low": 145.0,
      "close": 165.0,
      "volume": 1200000000
    },
    {
      "date": "2024-02-01",
      "open": 165.0,
      "high": 180.0,
      "low": 160.0,
      "close": 175.0,
      "volume": 1100000000
    }
  ]
}
```

**Year interval (interval=year)**
```json
{
  "symbol": "AAPL",
  "data": [
    {
      "date": "2023-01-01",
      "open": 130.0,
      "high": 180.0,
      "low": 125.0,
      "close": 175.0,
      "volume": 15000000000
    },
    {
      "date": "2024-01-01",
      "open": 175.0,
      "high": 200.0,
      "low": 170.0,
      "close": 195.0,
      "volume": 14500000000
    }
  ]
}
```

## 5. 边界情况处理

### 5.1 数据不足
- 如果某个时间段内没有交易数据（如周末、节假日），该时间段不会出现在结果中
- 前端图表会自动处理数据缺失，不会显示空白K线

### 5.2 日期边界
- Week: 使用 ISO 8601 标准（周一为一周的开始）
- Month: 使用自然月（1日到月末）
- Year: 使用自然年（1月1日到12月31日）

### 5.3 性能考虑
- Day 模式：直接查询，无聚合开销
- Week/Month/Year 模式：使用子查询获取 open/close
  - **当前实现**: 使用相关子查询，在小数据集（5年日线约1250条记录）上性能可接受
  - **性能阈值**: 如果查询时间超过 500ms，需要优化
  - **优化方案**:
    1. 使用窗口函数（FIRST_VALUE/LAST_VALUE）替代子查询
    2. 创建预聚合表定期更新
    3. 添加物化视图（需要 SQLite 扩展或迁移到 PostgreSQL）
- 已有索引 `idx_ohlc_symbol_date` 支持高效的日期范围查询

## 6. 未来扩展

### 6.1 可能的增强
- 添加更多时间粒度（如 5分钟、15分钟、1小时）
- 支持自定义时间窗口
- 添加技术指标叠加（MA、MACD等）

### 6.2 数据预聚合
- 如果查询性能成为瓶颈，可以考虑：
  - 定期预计算周/月/年数据并存储
  - 使用 SQLite 的物化视图（需要扩展）
  - 迁移到支持物化视图的数据库（如 PostgreSQL）

## 7. 风险与缓解

### 7.1 SQL 查询性能
- **风险**: 子查询可能在大数据集上变慢
- **缓解**:
  - 当前数据量（5年日线约1250条）较小，性能影响可控
  - 已有 `idx_ohlc_symbol_date` 索引支持查询
  - 性能要求明确：< 500ms，超过则需优化
  - 优化路径清晰：窗口函数 → 预聚合 → 物化视图

### 7.2 ISO 周边界处理
- **风险**: SQLite 的 `date(date, 'weekday 0', '-6 days')` 可能不完全符合 ISO 8601 周定义
- **缓解**:
  - 在单元测试中验证周边界的正确性
  - 测试跨年周（如2024年第1周可能包含2023年的日期）
  - 如果发现问题，使用 `strftime('%Y-%W', date)` 替代方案
  - **明确**: 周的 date 字段返回该周周一的日期，即使该周一属于上一年（如2024-12-30是周一，但可能属于2025年第1周，date 仍返回 2024-12-30）

### 7.3 前端类型变更
- **风险**: `TimeRange` 类型变更可能影响其他组件
- **缓解**:
  - 使用 TypeScript 编译检查
  - 全局搜索 `TimeRange` 确保所有使用点都已更新

### 7.4 用户习惯变化
- **风险**: 用户可能习惯了旧的时间跨度模式
- **缓解**:
  - 新设计更符合金融图表的标准做法（TradingView、Yahoo Finance 等都使用时间粒度）
  - 保留缩放和拖拽功能，用户仍可查看任意时间范围
  - 默认选择 'W'（周线），提供良好的初始体验

## 8. 总结

本设计通过在现有 API 上增加可选的 `interval` 参数，实现了从时间跨度到时间粒度的平滑过渡。设计保持了向后兼容性，同时为用户提供了更灵活的数据分析视角。实现相对简单，主要工作集中在 SQL 聚合逻辑和前端组件更新上。
