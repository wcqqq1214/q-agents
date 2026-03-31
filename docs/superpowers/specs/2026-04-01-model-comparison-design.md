---
name: Model Comparison Report Generation
description: Design for automated multi-model comparison and markdown report generation
type: design
---

# 量化预测模型对比报告生成设计

## 目标

创建自动化工具，对比三个量化预测模型（LightGBM、GRU、LSTM）的参数配置和预测效果，生成结构化的 Markdown 报告。

## 范围

- 扩展 `app/ml/model_registry.py` 添加对比逻辑
- 创建独立脚本 `scripts/ml/compare_models.py` 用于生成报告
- 输出标准化 Markdown 文档到 `docs/model_comparison_report.md`
- 支持任意股票代码和日期范围

## 架构

### 数据流

```
build_features(symbol)
    ↓
train_all_models(X, y)
    ├─ LightGBM 训练 → metrics + prediction
    ├─ GRU 训练 → metrics + prediction
    └─ LSTM 训练 → metrics + prediction
    ↓
generate_comparison_report(results, symbol, date_range)
    ↓ (返回结构化数据)
format_comparison_markdown(report)
    ↓ (返回 Markdown 字符串)
保存到文件
```

### 核心函数

#### 1. `generate_comparison_report(results, symbol, date_range)`

**输入：**
- `results`: `train_all_models()` 的返回值，包含每个模型的 model、metrics、prediction
- `symbol`: 股票代码（如 "AAPL"）
- `date_range`: 元组 `(start_date, end_date)`，格式 "YYYY-MM-DD"

**输出：**
```python
{
    "metadata": {
        "symbol": "AAPL",
        "date_range": ("2024-01-01", "2024-12-31"),
        "generated_at": "2026-04-01 10:30:00",
        "data_points": 252  # 交易日数量
    },
    "parameters": {
        "lightgbm": {
            "n_estimators": 200,
            "learning_rate": 0.01,
            "max_depth": 3,
            "num_leaves": 7,
            "min_child_samples": 50,
            "subsample": 0.6,
            "colsample_bytree": 0.5,
            "reg_alpha": 1.0,
            "reg_lambda": 1.0,
        },
        "gru": {
            "hidden_size": 32,
            "num_layers": 1,
            "dropout": 0.4,
            "seq_len": 15,
            "learning_rate": 0.0005,
            "weight_decay": 0.0001,
            "batch_size": 32,
            "max_epochs": 100,
        },
        "lstm": {
            "hidden_size": 32,
            "num_layers": 1,
            "dropout": 0.4,
            "seq_len": 15,
            "learning_rate": 0.0005,
            "weight_decay": 0.0001,
            "batch_size": 32,
            "max_epochs": 100,
        }
    },
    "metrics": {
        "lightgbm": {
            "mean_auc": 0.542,
            "mean_accuracy": 0.521,
            "fold_aucs": [0.53, 0.54, 0.55, 0.54, 0.53],
            "fold_accuracies": [0.51, 0.52, 0.53, 0.52, 0.51],
            "train_test_split": "TimeSeriesSplit_n5"
        },
        "gru": {
            "mean_auc": 0.551,
            "mean_accuracy": 0.535,
            "fold_aucs": [0.54, 0.55, 0.56, 0.55, 0.54],
            "fold_accuracies": [0.52, 0.53, 0.54, 0.53, 0.52],
            "seq_len": 15
        },
        "lstm": {
            "mean_auc": 0.548,
            "mean_accuracy": 0.532,
            "fold_aucs": [0.53, 0.55, 0.56, 0.54, 0.53],
            "fold_accuracies": [0.52, 0.53, 0.54, 0.53, 0.51],
            "seq_len": 15
        }
    },
    "predictions": {
        "lightgbm": 0.542,
        "gru": 0.518,
        "lstm": 0.521
    }
}
```

**职责：**
- 从 `results` 中提取参数（从模型对象和 config 中读取）
- 聚合 metrics 数据
- 计算元数据（生成时间、数据点数等）
- 返回结构化字典

#### 2. `format_comparison_markdown(report)`

**输入：** 上述结构化报告字典

**输出：** Markdown 字符串，包含以下部分：

1. **标题和元数据**
   - 股票代码、日期范围、生成时间、数据点数

2. **参数对比表**
   - 按模型列出所有关键参数
   - 突出差异（如 hidden_size、seq_len、正则化强度）

3. **性能指标表**
   - Mean AUC、Mean Accuracy
   - 各折的 AUC 和 Accuracy
   - 交叉验证策略说明

4. **最新预测信号表**
   - 三个模型的预测概率
   - 看涨/看跌判断（> 0.5 为看涨）
   - 信号一致性评估

5. **综合评定**
   - 各模型的优缺点
   - 推荐使用场景
   - 信号融合建议

**职责：**
- 将结构化数据转换为可读的 Markdown
- 使用表格、列表、代码块等格式
- 添加解释性文本和建议

### 脚本 `scripts/ml/compare_models.py`

**功能：**
```python
async def main(
    symbol: str = "AAPL",
    start_date: str = None,  # 默认过去 1 年
    end_date: str = None,    # 默认今天
    output_path: str = "docs/model_comparison_report.md"
):
    """
    1. 加载或生成特征数据
    2. 训练三个模型
    3. 生成对比报告
    4. 保存 Markdown 文件
    """
```

**使用方式：**
```bash
uv run python scripts/ml/compare_models.py --symbol AAPL --output docs/model_comparison_report.md
```

## 数据流和错误处理

### 成功路径
1. 特征数据可用 → 训练三个模型 → 生成报告 → 保存文件

### 错误处理
- 特征数据不足：抛出 `ValueError`，提示需要更多历史数据
- 模型训练失败：捕获异常，记录日志，继续其他模型
- 文件写入失败：抛出异常，提示磁盘空间或权限问题

## 输出示例

```markdown
# 量化预测模型对比报告

## 元数据
- **股票代码**: AAPL
- **数据周期**: 2024-01-01 ~ 2024-12-31
- **数据点数**: 252 个交易日
- **生成时间**: 2026-04-01 10:30:00

## 参数对比

### 数据处理
| 参数 | LightGBM | GRU | LSTM |
| --- | --- | --- | --- |
| 核心视角 | 截面特征、技术指标 | 时序演变、K线形态 | 时序演变、长短期记忆 |
| 历史回溯 | 无 | 15 天 | 15 天 |
| 归一化 | 无 | RobustScaler | RobustScaler |

### 网络结构
| 参数 | LightGBM | GRU | LSTM |
| --- | --- | --- | --- |
| 隐藏层大小 | N/A | 32 | 32 |
| 网络层数 | N/A | 1 | 1 |
| Dropout | 0.6 (subsample) | 0.4 | 0.4 |
| 参数量 | ~1000 | ~6000 | ~8000 |

### 训练配置
| 参数 | LightGBM | GRU | LSTM |
| --- | --- | --- | --- |
| 学习率 | 0.01 | 0.0005 | 0.0005 |
| 正则化 | L1/L2 | weight_decay | weight_decay |
| 批次大小 | N/A | 32 | 32 |
| 交叉验证 | TimeSeriesSplit(5) | TimeSeriesSplit(5) | TimeSeriesSplit(5) |

## 性能指标

| 指标 | LightGBM | GRU | LSTM |
| --- | --- | --- | --- |
| **Mean AUC** | 0.542 | 0.551 | 0.548 |
| **Mean Accuracy** | 0.521 | 0.535 | 0.532 |
| **Fold AUCs** | [0.53, 0.54, 0.55, 0.54, 0.53] | [0.54, 0.55, 0.56, 0.55, 0.54] | [0.53, 0.55, 0.56, 0.54, 0.53] |

## 最新预测信号

| 模型 | 预测概率 | 信号 | 置信度 |
| --- | --- | --- | --- |
| LightGBM | 54.2% | 看涨 | 中等 |
| GRU | 51.8% | 看涨 | 低 |
| LSTM | 52.1% | 看涨 | 低 |
| **融合信号** | **52.7%** | **看涨** | **中等** |

## 综合评定

### LightGBM
- **优点**: 训练速度快，对异常值容忍度高
- **缺点**: 无法捕捉时序依赖
- **推荐**: 作为基准信号

### GRU
- **优点**: 参数少，收敛稳定，不易过拟合
- **缺点**: 无法捕捉超长期记忆
- **推荐**: 时间序列主力预测器

### LSTM
- **优点**: 可捕捉长期依赖
- **缺点**: 参数多，易过拟合
- **推荐**: 辅助验证

### 信号融合建议
当三个模型预测同向（都 > 0.55 或都 < 0.45）时，置信度最高。
```

## 测试策略

1. **单元测试**
   - 测试 `generate_comparison_report()` 返回结构正确
   - 测试 `format_comparison_markdown()` 输出有效 Markdown

2. **集成测试**
   - 在小数据集上运行完整流程
   - 验证输出文件格式和内容

3. **手动验证**
   - 在真实股票数据上运行
   - 检查参数表、指标表、预测信号的准确性

## 依赖和约束

- 依赖：`app/ml/model_registry.py`、`app/ml/features.py`、`app/ml/dl_config.py`
- 约束：需要至少 252 个交易日的历史数据
- 性能：完整流程预计 5-15 分钟（取决于数据量和硬件）

## 后续扩展

- 支持多个股票的批量对比
- 添加可视化图表（AUC 曲线、预测分布等）
- 集成到 FastAPI 后端作为 `/api/ml/compare` 端点
- 定期自动生成报告并存档
