# Crypto K线图异常数据修复设计

**日期:** 2026-03-22
**状态:** 待审批

## 问题描述

### Bug现象
在crypto K线图中，当选择1Week、1Month、All时间范围时，图表出现严重渲染问题：
- 2023年6-7月位置出现极端异常的"擎天柱"插针
- 最高价达到 35,000,000 USDT（实际BTC价格约3万）
- Y轴被拉伸到千万级别
- 正常价格走势被压缩成贴近X轴的一条线

### 根本原因
数据库中存在3条脏数据：

1. **2023-06-26 (1W)**: high = 1,122,986 (正常应为3万左右)
2. **2023-07-03 (1W)**: high = 36,162,247 (异常值)
3. **2023-08-07 (1W)**: high = 1,612,144, low = 0.1 (异常高低价)

这些异常数据来自OKX API，可能原因：
- API返回错误数据
- 极端流动性问题导致的"插针"
- 数据传输错误

### 影响范围
- 1Week (1W) 时间范围：200条记录中有3条异常
- 1Month (1M) 时间范围：47条记录中有2条异常
- All (1Y) 时间范围：继承1M的异常数据
- 短期范围(15M, 1H, 4H, 1D)：未发现异常

## 解决方案

采用 **A (数据清洗) + D (数据验证)** 组合方案：

### 方案A：清理现有脏数据
1. 删除已识别的3条异常记录
2. 重新从OKX API获取这些时间段的正确数据

### 方案D：添加数据验证机制
在数据入库前进行多层验证，防止未来再次出现异常数据

## 数据验证规则设计

### 验证层级

数据验证在 `fetch_crypto_ohlc.py` 的数据处理流程中执行，在存入数据库之前进行。

### 验证规则

#### 1. 绝对值底线检查
**目的**: 防止明显不合理的价格值

- `low > 0`: 价格必须为正数
- `open > 0`, `high > 0`, `close > 0`: 所有价格必须为正数
- **绝对价格上限**:
  - BTC-USDT: `high < 500,000` (当前约8万，留足6倍空间)
  - ETH-USDT: `high < 50,000` (当前约3千，留足15倍空间)

**拒绝条件**: 任一价格 ≤ 0 或超过上限

#### 2. K线逻辑一致性检查
**目的**: 确保K线数据符合基本定义

- `high >= open`
- `high >= close`
- `low <= open`
- `low <= close`
- `high >= low`

**拒绝条件**: 任一条件不满足

#### 3. 单根K线振幅检查
**目的**: 防止单根K线内部的极端波动

- `high / low < 3.0`: 单根K线最高价不超过最低价的3倍
- 对于主流币(BTC/ETH)的日线及以上级别，单根K线内300%的波动极其罕见

**拒绝条件**: `high / low >= 3.0`

#### 4. 跳空异常检查（与前一根K线对比）
**目的**: 防止相邻K线之间的极端跳空

计算当前K线与前一根K线的价格变化：
```python
# 使用close价格计算涨跌幅
change_pct = abs(current_close - prev_close) / prev_close

# 阈值：75%
if change_pct > 0.75:
    reject
```

**拒绝条件**: 相邻K线收盘价变化超过75%

**注意**: 此规则仅在有前一根K线数据时执行（第一根K线跳过）

#### 5. 批量数据一致性检查
**目的**: 检测整批数据中的离群值

对于一批数据（如300根K线）：
- 计算所有high的中位数 `median_high`
- 检查每根K线: `high < median_high * 10`

**拒绝条件**: 单根K线的high超过中位数的10倍


### 验证流程

```python
def validate_candle(candle: dict, prev_candle: dict = None, symbol: str = "BTC-USDT") -> tuple[bool, str]:
    """验证单根K线数据
    
    Returns:
        (is_valid, error_message)
    """
    o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
    
    # 1. 绝对值检查
    if l <= 0 or o <= 0 or h <= 0 or c <= 0:
        return False, "Price must be positive"
    
    # 价格上限
    price_limits = {
        "BTC-USDT": 500000,
        "ETH-USDT": 50000
    }
    limit = price_limits.get(symbol, 1000000)
    if h > limit:
        return False, f"High price {h} exceeds limit {limit}"
    
    # 2. K线逻辑一致性
    if not (h >= o and h >= c and l <= o and l <= c and h >= l):
        return False, "K-line logic inconsistency"
    
    # 3. 单根振幅检查
    if h / l >= 3.0:
        return False, f"Amplitude too large: high/low = {h/l:.2f}"
    
    # 4. 跳空检查
    if prev_candle:
        prev_close = prev_candle['close']
        change_pct = abs(c - prev_close) / prev_close
        if change_pct > 0.75:
            return False, f"Jump too large: {change_pct*100:.1f}%"
    
    return True, ""

def validate_batch(candles: list[dict], symbol: str) -> list[dict]:
    """批量验证并过滤异常数据"""
    if not candles:
        return []
    
    # 5. 批量一致性检查
    highs = [c['high'] for c in candles]
    median_high = sorted(highs)[len(highs) // 2]
    
    valid_candles = []
    prev_candle = None
    
    for candle in candles:
        # 批量离群值检查
        if candle['high'] > median_high * 10:
            logger.warning(f"Outlier detected: high={candle['high']}, median={median_high}")
            continue
        
        # 单根验证
        is_valid, error = validate_candle(candle, prev_candle, symbol)
        if is_valid:
            valid_candles.append(candle)
            prev_candle = candle
        else:
            logger.warning(f"Invalid candle at {candle['date']}: {error}")
    
    return valid_candles
```

## 实施步骤

### 步骤1: 创建数据验证模块

创建 `app/utils/crypto_validator.py`，包含上述验证函数。

### 步骤2: 修改数据获取脚本

修改 `scripts/fetch_crypto_ohlc.py`：
1. 导入验证模块
2. 在存入数据库前调用 `validate_batch()`
3. 记录被拒绝的数据到日志

### 步骤3: 清理现有脏数据

创建清理脚本 `scripts/clean_crypto_anomalies.py`：

```python
"""清理crypto数据库中的异常数据"""
from app.database.crypto_ohlc import get_conn

def clean_anomalies():
    conn = get_conn()
    
    # 删除已识别的异常记录
    anomalies = [
        ("BTC-USDT", 1687708800000, "1W"),  # 2023-06-26
        ("BTC-USDT", 1688313600000, "1W"),  # 2023-07-03
        ("BTC-USDT", 1691337600000, "1W"),  # 2023-08-07
    ]
    
    for symbol, timestamp, bar in anomalies:
        conn.execute(
            "DELETE FROM crypto_ohlc WHERE symbol = ? AND timestamp = ? AND bar = ?",
            (symbol, timestamp, bar)
        )
        print(f"Deleted: {symbol} {bar} at timestamp {timestamp}")
    
    # 同时清理1M中的异常数据
    conn.execute("""
        DELETE FROM crypto_ohlc 
        WHERE symbol = 'BTC-USDT' 
        AND bar = '1M' 
        AND high > 1000000
    """)
    
    conn.commit()
    conn.close()
    print("Cleanup completed!")

if __name__ == "__main__":
    clean_anomalies()
```

### 步骤4: 重新获取正确数据

运行修改后的 `fetch_crypto_ohlc.py`，重新获取被删除时间段的数据。

### 步骤5: 验证修复结果

检查数据库，确认：
1. 异常数据已删除
2. 新数据通过验证
3. K线图正常显示


## 测试策略

### 单元测试

测试 `crypto_validator.py` 中的验证函数：

```python
# tests/test_crypto_validator.py

def test_validate_candle_positive_prices():
    """测试价格必须为正"""
    candle = {"open": 30000, "high": 31000, "low": -100, "close": 30500}
    is_valid, error = validate_candle(candle)
    assert not is_valid
    assert "positive" in error.lower()

def test_validate_candle_logic_consistency():
    """测试K线逻辑一致性"""
    candle = {"open": 30000, "high": 29000, "low": 31000, "close": 30500}
    is_valid, error = validate_candle(candle)
    assert not is_valid
    assert "logic" in error.lower()

def test_validate_candle_amplitude():
    """测试振幅检查"""
    candle = {"open": 30000, "high": 90000, "low": 10000, "close": 50000}
    is_valid, error = validate_candle(candle)
    assert not is_valid
    assert "amplitude" in error.lower()

def test_validate_candle_jump():
    """测试跳空检查"""
    prev = {"close": 30000}
    current = {"open": 50000, "high": 55000, "low": 49000, "close": 53000}
    is_valid, error = validate_candle(current, prev)
    assert not is_valid
    assert "jump" in error.lower()

def test_validate_batch_outlier():
    """测试批量离群值检查"""
    candles = [
        {"high": 30000, "low": 29000, "open": 29500, "close": 29800},
        {"high": 31000, "low": 30000, "open": 30200, "close": 30800},
        {"high": 3000000, "low": 29500, "open": 30000, "close": 30500},  # 离群值
    ]
    valid = validate_batch(candles, "BTC-USDT")
    assert len(valid) == 2  # 离群值被过滤
```

### 集成测试

1. **清理脚本测试**:
   - 运行 `clean_crypto_anomalies.py`
   - 验证3条异常记录被删除
   - 验证1M中的异常数据被删除

2. **数据获取测试**:
   - 运行 `fetch_crypto_ohlc.py`
   - 验证新数据通过验证
   - 验证日志中记录了验证过程

3. **端到端测试**:
   - 在前端选择1Week时间范围
   - 缩放和左移K线图
   - 验证不再出现"擎天柱"异常
   - 验证Y轴刻度正常

## 成功标准

### 数据质量
- ✓ 数据库中无价格 ≤ 0 的记录
- ✓ 数据库中无价格超过上限的记录
- ✓ 所有K线满足逻辑一致性
- ✓ 无单根K线振幅 ≥ 3倍
- ✓ 无相邻K线跳空 > 75%

### 用户体验
- ✓ 1Week/1Month/All时间范围K线图正常显示
- ✓ 缩放和左移操作流畅，无异常
- ✓ Y轴刻度合理，价格走势清晰可见
- ✓ 无"擎天柱"插针现象

### 系统健壮性
- ✓ 数据验证模块正常工作
- ✓ 异常数据被拒绝并记录日志
- ✓ 未来数据获取自动过滤异常值

## 风险和注意事项

### 风险1: 过度严格的验证规则
**风险**: 验证规则可能拒绝真实的极端行情（如黑天鹅事件）

**缓解措施**:
- 使用相对宽松的阈值（如75%跳空，而非10%）
- 记录所有被拒绝的数据到日志，便于人工审查
- 提供手动覆盖机制（如果需要）

### 风险2: 历史数据缺失
**风险**: 删除异常数据后，OKX API可能无法返回该时间段的正确数据

**缓解措施**:
- 在删除前备份异常数据
- 如果API无法返回数据，考虑使用插值修复
- 记录数据缺失情况

### 风险3: 不同币种的差异
**风险**: BTC和ETH的价格范围和波动性不同

**缓解措施**:
- 为每个币种设置独立的价格上限
- 考虑使用相对阈值而非绝对值（如基于历史波动率）
- 定期审查和调整验证规则

## 未来改进

1. **动态阈值**: 基于历史波动率动态调整验证阈值
2. **更多币种支持**: 扩展到更多加密货币
3. **实时监控**: 添加数据质量监控仪表板
4. **自动修复**: 对于可修复的异常（如明显的小数点错误），自动修正而非拒绝

## 结论

通过实施数据清洗和验证机制，我们可以：
1. 彻底解决当前的K线图异常显示问题
2. 防止未来再次出现类似问题
3. 提升整体数据质量和系统可靠性

该方案平衡了数据质量和灵活性，既能过滤明显的脏数据，又不会过度限制真实的市场波动。
