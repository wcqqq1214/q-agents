---
name: agent-decision-history
description: AI决策过程完整记录系统，使用SQLite存储agent推理历史、工具调用和决策结果
type: design
date: 2026-03-21
---

# AI决策过程记录系统设计

## 1. 背景与目标

### 1.1 当前状态
- 系统使用多agent架构（Quant + News + Social → CIO综合决策）
- 报告以JSON文件形式存储在 `data/reports/{timestamp}_{asset}/` 目录
- 缺乏对agent推理过程、工具调用、决策链条的系统化记录

### 1.2 设计目标
**核心需求**：完整记录AI决策过程的所有细节，为未来的学习和改进奠定基础

**记录范围**：
- 推理链条：CIO为什么选择看涨/看跌，如何权衡冲突信号
- 工具使用模式：查询了哪些数据源，使用了什么参数
- 预测结果：推荐了什么 vs 市场实际发生了什么
- 中间agent推理：Quant/News/Social各自的完整推理过程

**非目标**（本期不实现）：
- 基于历史记录的自动学习机制
- 决策模式识别和准确率统计
- 预测结果的自动回测

## 2. 技术方案

### 2.1 存储方案选择

**选定方案：混合设计（方案C）**

核心思路：主表存JSON（完整性），辅助表存结构化数据（查询性）

**优势**：
1. **兼顾完美回放与高效查询**
   - messages存为JSON：100%还原上下文，便于debug
   - tool_calls独立表：支持复杂查询（如"统计工具失败率"）

2. **为未来学习机制铺路**
   - 主表保证底层数据完整性
   - 预留decision_outcomes表，后续直接写入数据即可

3. **符合业界标准**
   - 参考LangSmith/Langfuse的设计模式
   - 原始trace + 关键指标提取

### 2.2 数据格式标准化

**messages存储格式：OpenAI标准格式**

```json
[
  {
    "role": "system",
    "content": "You are a quantitative analyst..."
  },
  {
    "role": "user",
    "content": "Analyze AAPL stock"
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_stock_data",
          "arguments": "{\"ticker\": \"AAPL\", \"period\": \"3mo\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_abc123",
    "content": "{\"data\": [...]}"
  }
]
```

**选择理由**：
- 避免框架绑定（LangChain特有格式会导致迁移困难）
- 前端友好（主流聊天组件原生支持）
- 保留核心上下文（tool_calls完整记录）

## 3. 数据库设计

### 3.1 数据库文件
- **位置**：`data/agent_history.db`
- **类型**：SQLite 3
- **理由**：创建新数据库，与现有finance_data.db分离，职责清晰

### 3.2 表结构

#### 3.2.1 analysis_runs（分析运行元数据）

```sql
CREATE TABLE analysis_runs (
    run_id TEXT PRIMARY KEY,           -- 格式：20260321_143052
    asset TEXT NOT NULL,               -- 资产代码：AAPL, BTC-USD
    query TEXT NOT NULL,               -- 用户原始查询
    timestamp DATETIME NOT NULL,       -- 运行时间（UTC+8）
    final_decision TEXT,               -- CIO最终决策文本
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_runs_asset ON analysis_runs(asset);
CREATE INDEX idx_runs_timestamp ON analysis_runs(timestamp);
```

**字段说明**：
- `run_id`：复用现有的时间戳格式（YYYYMMDD_HHMMSS）
- `asset`：标准化后的资产代码（大写，去除特殊字符）
- `query`：用户原始输入，保留语言和格式
- `final_decision`：CIO综合决策的完整文本

#### 3.2.2 agent_executions（Agent执行记录）

```sql
CREATE TABLE agent_executions (
    execution_id TEXT PRIMARY KEY,     -- UUID
    run_id TEXT NOT NULL,              -- 关联analysis_runs
    agent_type TEXT NOT NULL,          -- 'quant', 'news', 'social', 'cio'
    messages_json TEXT NOT NULL,       -- OpenAI标准格式的完整对话历史
    output_text TEXT,                  -- Agent最终输出文本
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    duration_seconds REAL,
    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
);

CREATE INDEX idx_exec_run ON agent_executions(run_id);
CREATE INDEX idx_exec_agent ON agent_executions(agent_type);
```

**字段说明**：
- `execution_id`：使用UUID确保全局唯一
- `agent_type`：枚举值 ['quant', 'news', 'social', 'cio']
- `messages_json`：完整的ReAct循环对话历史（JSON数组）
- `output_text`：agent的最终输出（从最后一条assistant消息提取）
- `duration_seconds`：执行耗时，用于性能分析

#### 3.2.3 tool_calls（工具调用索引）

```sql
CREATE TABLE tool_calls (
    call_id TEXT PRIMARY KEY,          -- UUID
    execution_id TEXT NOT NULL,        -- 关联agent_executions
    tool_name TEXT NOT NULL,           -- 'get_stock_data', 'search_news_with_tavily'
    arguments_json TEXT NOT NULL,      -- 工具参数（JSON对象）
    result_json TEXT,                  -- 工具返回结果（JSON）
    status TEXT NOT NULL,              -- 'success', 'failed'
    error_message TEXT,                -- 失败时的错误信息
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES agent_executions(execution_id)
);

CREATE INDEX idx_tool_exec ON tool_calls(execution_id);
CREATE INDEX idx_tool_name ON tool_calls(tool_name);
CREATE INDEX idx_tool_status ON tool_calls(status);
```

**字段说明**：
- `tool_name`：工具函数名称
- `arguments_json`：调用参数（如 `{"ticker": "AAPL", "period": "3mo"}`）
- `result_json`：工具返回的完整结果
- `status`：成功/失败状态，用于统计工具可靠性

#### 3.2.4 decision_outcomes（预测结果跟踪）

```sql
CREATE TABLE decision_outcomes (
    outcome_id TEXT PRIMARY KEY,       -- UUID
    run_id TEXT NOT NULL,              -- 关联analysis_runs
    predicted_direction TEXT,          -- 'bullish', 'bearish', 'neutral'
    actual_outcome TEXT,               -- 事后标注（预留）
    evaluation_date DATE,              -- 评估日期（预留）
    notes TEXT,                        -- 备注（预留）
    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
);
```

**说明**：本期仅建表，不实现写入逻辑，为未来的回测功能预留

## 4. 系统架构

### 4.1 目录结构

```
app/database/
├── agent_history.py          # 数据库操作层
│   ├── init_db()            # 初始化数据库和表结构
│   ├── save_analysis_run()  # 保存分析运行
│   ├── save_agent_execution() # 保存agent执行
│   ├── save_tool_call()     # 保存工具调用
│   ├── query_analysis_runs() # 查询分析列表
│   ├── query_run_detail()   # 查询单次分析详情
│   ├── query_agent_messages() # 查询agent对话历史
│   └── query_tool_calls()   # 查询工具调用记录
│
├── message_adapter.py        # 消息格式转换
│   └── convert_messages_to_standard() # LangChain -> OpenAI格式
│
app/api/routes/
└── history.py               # FastAPI路由
    ├── GET /api/analysis-runs
    ├── GET /api/analysis-runs/{run_id}
    ├── GET /api/agent-executions/{execution_id}/messages
    └── GET /api/tool-calls
```

### 4.2 数据流设计

#### 4.2.1 写入流程

```
graph_multi.py (多agent编排)
    ↓
每个agent执行完毕后
    ↓
message_adapter.convert_messages_to_standard()
    ↓ (转换为OpenAI格式)
agent_history.save_agent_execution()
    ↓ (同时解析tool_calls)
agent_history.save_tool_call() (批量)
    ↓
SQLite: agent_history.db
```

**关键点**：
- 在每个agent的ReAct循环结束后立即写入
- 转换层（message_adapter）负责格式标准化
- tool_calls从messages中提取并单独存储

#### 4.2.2 查询流程

```
前端/脚本
    ↓
FastAPI /api/history/*
    ↓
agent_history.query_*()
    ↓
SQLite查询 + JSON解析
    ↓
返回结构化数据
```

## 5. API设计

### 5.1 基础查询API

#### 5.1.1 查询分析运行列表

```
GET /api/analysis-runs?asset=AAPL&date_from=2026-01-01&date_to=2026-03-21&limit=50&offset=0
```

**响应**：
```json
{
  "total": 123,
  "items": [
    {
      "run_id": "20260321_143052",
      "asset": "AAPL",
      "query": "分析AAPL的最新股价和新闻",
      "timestamp": "2026-03-21T14:30:52+08:00",
      "final_decision": "综合技术面和新闻面...",
      "agent_count": 4
    }
  ]
}
```

#### 5.1.2 获取单次分析详情

```
GET /api/analysis-runs/{run_id}
```

**响应**：
```json
{
  "run_id": "20260321_143052",
  "asset": "AAPL",
  "query": "分析AAPL的最新股价和新闻",
  "timestamp": "2026-03-21T14:30:52+08:00",
  "final_decision": "综合技术面和新闻面...",
  "agents": [
    {
      "execution_id": "uuid-1",
      "agent_type": "quant",
      "output_text": "技术分析报告...",
      "start_time": "2026-03-21T14:30:52+08:00",
      "end_time": "2026-03-21T14:31:15+08:00",
      "duration_seconds": 23.5,
      "tool_calls_count": 3
    },
    {
      "execution_id": "uuid-2",
      "agent_type": "news",
      "output_text": "新闻情绪分析...",
      "start_time": "2026-03-21T14:30:52+08:00",
      "end_time": "2026-03-21T14:31:20+08:00",
      "duration_seconds": 28.2,
      "tool_calls_count": 2
    }
  ]
}
```

#### 5.1.3 获取agent完整对话历史

```
GET /api/agent-executions/{execution_id}/messages
```

**响应**：
```json
{
  "execution_id": "uuid-1",
  "agent_type": "quant",
  "messages": [
    {
      "role": "system",
      "content": "You are a quantitative analyst..."
    },
    {
      "role": "user",
      "content": "Analyze AAPL stock"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [...]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "{\"data\": [...]}"
    }
  ]
}
```

### 5.2 工具调用分析API

#### 5.2.1 查询工具调用记录

```
GET /api/tool-calls?tool_name=get_stock_data&status=failed&date_from=2026-03-01&limit=50
```

**响应**：
```json
{
  "total": 15,
  "items": [
    {
      "call_id": "uuid-123",
      "execution_id": "uuid-1",
      "tool_name": "get_stock_data",
      "arguments": {
        "ticker": "AAPL",
        "period": "3mo"
      },
      "status": "failed",
      "error_message": "Connection timeout",
      "timestamp": "2026-03-21T14:31:05+08:00"
    }
  ]
}
```

#### 5.2.2 工具使用统计

```
GET /api/tool-calls/stats?date_from=2026-03-01&date_to=2026-03-21
```

**响应**：
```json
{
  "period": {
    "from": "2026-03-01",
    "to": "2026-03-21"
  },
  "tools": [
    {
      "tool_name": "get_stock_data",
      "total_calls": 450,
      "success_count": 445,
      "failed_count": 5,
      "success_rate": 0.989,
      "avg_duration_seconds": 2.3
    },
    {
      "tool_name": "search_news_with_tavily",
      "total_calls": 380,
      "success_count": 375,
      "failed_count": 5,
      "success_rate": 0.987,
      "avg_duration_seconds": 3.1
    }
  ]
}
```

## 6. 实现计划

### 6.1 迁移策略

**阶段1：新增SQLite存储（双写）**
- 保留现有JSON文件生成逻辑
- 新增SQLite写入逻辑
- 验证数据完整性
- 时间：1-2天

**阶段2：切换到SQLite（单写）**
- 移除JSON文件生成代码
- 所有读取改为从SQLite查询
- 清理`data/reports/`目录结构
- 时间：1天

**阶段3：历史数据迁移（可选）**
- 编写脚本将现有JSON报告导入SQLite
- 保留JSON文件作为备份
- 时间：按需执行

### 6.2 实现优先级

**P0（核心功能）**：
1. 数据库表结构创建
2. message_adapter转换层
3. agent_history数据库操作层
4. graph_multi.py集成写入逻辑
5. 基础查询API

**P1（增强功能）**：
1. 工具调用统计API
2. 前端查询界面
3. 历史数据迁移脚本

**P2（未来扩展）**：
1. decision_outcomes写入逻辑
2. 决策模式分析
3. 自动学习机制

## 7. 技术细节

### 7.1 消息格式转换

**LangChain消息类型映射**：
- `SystemMessage` → `{"role": "system", "content": "..."}`
- `HumanMessage` → `{"role": "user", "content": "..."}`
- `AIMessage` → `{"role": "assistant", "content": "...", "tool_calls": [...]}`
- `ToolMessage` → `{"role": "tool", "tool_call_id": "...", "content": "..."}`

**tool_calls提取**：
从AIMessage的`tool_calls`属性提取，转换为OpenAI格式：
```python
{
  "id": "call_abc123",
  "type": "function",
  "function": {
    "name": "get_stock_data",
    "arguments": "{\"ticker\": \"AAPL\"}"
  }
}
```

### 7.2 时间戳处理

- 所有时间戳使用UTC+8（与现有run_id保持一致）
- 数据库存储使用ISO 8601格式
- API返回时包含时区信息

### 7.3 错误处理

- 数据库写入失败不应阻塞agent执行
- 使用try-except包裹写入逻辑
- 记录错误日志但继续执行

### 7.4 性能考虑

- messages_json字段可能较大（几十KB），但SQLite TEXT类型支持最大2GB
- 索引覆盖常用查询字段（asset, timestamp, tool_name）
- 考虑定期归档历史数据（如6个月前的记录）

## 8. 测试计划

### 8.1 单元测试
- message_adapter转换正确性
- agent_history CRUD操作
- 边界情况（空messages、失败的tool_calls）

### 8.2 集成测试
- 完整的分析流程写入
- API端点响应正确性
- 并发写入安全性

### 8.3 数据验证
- 对比JSON报告和SQLite记录的一致性
- 验证tool_calls提取的完整性
- 检查时间戳和duration计算

## 9. 风险与缓解

### 9.1 数据丢失风险
- **风险**：SQLite写入失败导致记录丢失
- **缓解**：阶段1保留JSON双写，验证稳定后再切换

### 9.2 性能影响
- **风险**：数据库写入增加agent执行延迟
- **缓解**：异步写入（后台线程），不阻塞主流程

### 9.3 存储空间
- **风险**：完整messages占用大量空间
- **缓解**：定期归档，压缩历史数据

## 10. 未来扩展

### 10.1 学习机制（Phase 2）
- 基于decision_outcomes的准确率统计
- 识别成功/失败的决策模式
- 自动调整agent权重

### 10.2 可视化（Phase 3）
- 决策流程图（Quant → News → Social → CIO）
- 工具调用时间线
- 准确率趋势图

### 10.3 导出功能
- 导出为Markdown报告
- 生成决策复盘文档
- 支持数据分析（Pandas DataFrame）
