# finance-agent

[English](README.md) | 中文

---

基于 Python 3.13、LangChain 与 LangGraph 的多智能体金融分析系统，采用 Fan-out / Fan-in 拓扑（Quant 与 News 并行，最后由 CIO 汇总），通过 Claude/OpenAI 与 MCP 服务器获取行情/指标与新闻并生成报告。同时，独立的 Social Agent 会抓取 Reddit 讨论并生成结构化的散户情绪报告。

## 功能特性

- **多智能体架构**: Quant 和 News 智能体并行执行，CIO 汇总分析
- **市场数据分析**: 实时报价、历史数据及技术指标（SMA、MACD、布林带）
- **新闻情报**: 多源新闻聚合（DuckDuckGo、Tavily）与情绪分析
- **社交情绪**: Reddit 讨论分析，获取散户投资者情绪
- **机器学习预测**: 基于 LightGBM 的量化模型，支持 SHAP 可解释性
- **事件记忆（RAG）**: ChromaDB 驱动的事件数据库，提供历史上下文
- **预测市场**: Polymarket 集成，获取市场情绪信号
- **智能新闻过滤**: 两层过滤（规则 + LLM）降低噪音
- **自动化报告**: 结构化 JSON/Markdown 报告，支持多语言

## 技术栈

- **语言**: Python 3.13
- **AI 框架**: `langchain`, `langgraph`, `langchain-anthropic`, `langchain-openai`
- **机器学习/数据**: `pandas`, `numpy`, `lightgbm`, `shap`, `scikit-learn`, `pandas-ta`
- **数据源**: `yfinance`, `tavily-python`, `ddgs`（DuckDuckGo）— 均经 MCP 服务器
- **向量数据库**: `chromadb`, `langchain-chroma`
- **配置**: `python-dotenv`

## 环境初始化

### 前置要求

- Python 3.13
- [uv](https://docs.astral.sh/uv/)（推荐）或 `pip`

### 1. 克隆并进入仓库

```bash
git clone <你的仓库地址>
cd finance-agent
```

### 2. 创建并激活虚拟环境

**使用 uv：**

```bash
uv venv
source .venv/bin/activate   # Linux / macOS
# 或  .venv\Scripts\activate  # Windows
```

**使用系统 Python：**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

**使用 uv（在项目根目录）：**

```bash
uv sync
```

**使用 pip：**

```bash
pip install -e .
```

若不使用 `pip install -e .`，可依据 `pyproject.toml` 中的依赖自行安装。

### 4. 配置环境变量

复制环境变量模板并填入你的 API 密钥：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件，填入你的 API 密钥：

**必需的 API 密钥：**
- **CLAUDE_API_KEY**: 从 [Anthropic Console](https://console.anthropic.com/) 获取 - 智能体的主要 LLM
- **OPENAI_API_KEY**: 从 [OpenAI Platform](https://platform.openai.com/) 获取 - 用于 embeddings（text-embedding-3-small）
- **POLYGON_API_KEY**: 从 [Polygon.io](https://polygon.io/) 获取 - 用于金融数据
- **TAVILY_API_KEY**: 从 [Tavily](https://tavily.com/) 获取 - 用于新闻搜索

**可选配置：**
- **LLM_PROVIDER**: 选择 `claude`（默认）或 `openai`
- **LLM_TEMPERATURE**: 控制响应随机性（默认：0.0）
- **EMBEDDING_PROVIDER**: 选择 embedding 提供商（默认：`openai`）
- MCP 服务器地址（本地运行使用默认值即可）
- MiniMax API（备用 LLM 提供商）

`.env.example` 文件包含了所有可用的配置选项及占位符值。

### 5. MCP 服务器（行情/指标与新闻工具必需）

行情（含历史+指标）与新闻工具均通过 MCP 协议从独立服务器获取数据，不再直接调用 yfinance 或 DuckDuckGo。运行 Agent 前需先启动 MCP 服务器。

**终端 1 — 启动 MCP 服务器：**

```bash
# 启动所有 MCP 服务器（市场数据 + 新闻搜索）
bash scripts/start_mcp_servers.sh
```

市场数据服务器默认监听 `http://127.0.0.1:8000/mcp`，新闻搜索服务器监听 `http://127.0.0.1:8001/mcp`。

**终端 2 — 若 MCP 服务器地址不同，在 `.env` 中配置：**

```bash
MCP_MARKET_DATA_URL=http://127.0.0.1:8000/mcp
MCP_NEWS_SEARCH_URL=http://127.0.0.1:8001/mcp
```

## 运行 Agent

### 交互式命令行（推荐快速测试）

```bash
uv run python -m scripts.manual_run
```

然后输入自然语言问题：
- 中文："帮我看一下 AAPL 的最新股价和最近重要新闻"
- 英文："Analyze AAPL stock with latest news"

输入 `exit` 或 `quit` 退出。

### 在 Python 中单次调用

```python
from app.graph_multi import run_once
final_state = run_once("分析 NVDA 与 BTC-USD")
print(final_state["final_decision"])
```

### 批量处理

批量处理多个股票代码：

```bash
uv run python scripts/batch_process.py
```

### 每日采集器

自动化每日新闻收集与分析：

```bash
uv run python scripts/daily_harvester.py
```

## 验证工具（可选）

行情/指标与新闻工具（需先启动 MCP 服务器）：

```bash
uv run python -c "from app.tools.finance_tools import get_us_stock_quote; from pprint import pprint; pprint(get_us_stock_quote.invoke({'ticker': 'AAPL'}))"
```

新闻搜索：

```bash
uv run python -c "from app.tools.finance_tools import search_news_with_duckduckgo; from pprint import pprint; pprint(search_news_with_duckduckgo.invoke({'query': 'AAPL', 'limit': 2}))"
```

历史 + 指标（SMA/MACD/布林带，经 MCP）：

```bash
uv run python -c "from app.tools.finance_tools import get_stock_data; print(get_stock_data.invoke({'ticker': 'NVDA', 'period': '3mo'}))"
```

## MCP 服务器

系统使用模型上下文协议（MCP）服务器来暴露金融数据和新闻搜索能力。

### 架构

**市场数据服务器** (`mcp_servers/market_data/`)
- 端口：8000
- 工具：`get_us_stock_quote`、`get_stock_data`（含 SMA、MACD、布林带）
- 依赖：yfinance、pandas

**新闻搜索服务器** (`mcp_servers/news_search/`)
- 端口：8001
- 工具：`search_news_with_duckduckgo`、`search_news_with_tavily`
- 依赖：ddgs、tavily-python

### 服务器管理

启动所有服务器：
```bash
bash scripts/start_mcp_servers.sh
```

停止所有服务器：
```bash
bash scripts/stop_mcp_servers.sh
```

启动单个服务器：
```bash
# 市场数据
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/market_data/main.py

# 新闻搜索
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/news_search/main.py
```

### 故障排查

**端口已被占用：**
```bash
lsof -i :8000  # 或 :8001
kill <PID>
```

**服务器无响应：**
```bash
ps aux | grep mcp_servers
```

**Tavily API 密钥缺失：**
从 https://tavily.com 获取 API 密钥并添加到 `.env`：`TAVILY_API_KEY=your_key_here`

## 高级功能

### 机器学习量化分析

训练和评估 LightGBM 价格预测模型：

```bash
uv run python scripts/run_ml_quant_metrics.py
```

功能包括：
- 技术指标（SMA、MACD、RSI、布林带、ATR）
- 成交量分析
- SHAP 可解释性分析
- 时间序列交叉验证

### 事件记忆（RAG）

构建和查询事件记忆数据库：

```bash
# 为特定股票构建事件记忆
uv run python scripts/build_event_memory_batch.py

# 查询事件记忆
uv run python scripts/query_event_memory.py

# 检查事件记忆
uv run python scripts/inspect_event_memory.py
```

系统使用 ChromaDB 存储和检索历史事件，支持语义搜索。

### Polymarket 集成

探索预测市场获取情绪信号：

```bash
# 探索 Polymarket 数据
uv run python scripts/explore_polymarket.py

# 按类别搜索
uv run python scripts/search_polymarket_by_category.py
```

### 智能新闻过滤

两层过滤管道：
- **Layer 0**: 基于规则的过滤（免费、即时）- 过滤约 25-35% 的无关新闻
- **Layer 1**: 基于 LLM 的相关性评分 - 深度语义分析

通过管道处理新闻：

```bash
uv run python scripts/process_layer1.py
```

## 项目结构

### 核心智能体系统
- `app/graph_multi.py` — 多智能体 LangGraph（Quant + News 并行，CIO 汇总）
- `app/state.py` — 多智能体图使用的 `AgentState`
- `app/llm_config.py` — LLM 配置（Claude/OpenAI）
- `app/embedding_config.py` — Embedding 配置

### 工具与数据源
- `app/tools/finance_tools.py` — LangChain 工具（均经 MCP）：报价、历史数据、新闻搜索
- `app/tools/enhanced_tools.py` — 增强工具，提供额外功能
- `app/tools/quant_tool.py` — 量化分析工具
- `app/mcp_client/finance_client.py` — MCP 客户端，调用 MCP 服务器

### MCP 服务器
- `mcp_servers/market_data/` — 市场数据 MCP 服务器（yfinance 封装）
  - `main.py` — 服务器入口
  - `indicators.py` — 技术指标（SMA、MACD、布林带）
- `mcp_servers/news_search/` — 新闻搜索 MCP 服务器
  - `main.py` — 服务器入口
  - `duckduckgo_impl.py` — DuckDuckGo 搜索实现
  - `tavily_impl.py` — Tavily 搜索实现

### 社交情绪分析
- `app/social/graph_social.py` — Social Agent 的 LangGraph：Reddit 抓取 → NLP → 报告导出
- `app/social/entrypoint.py` — 对外入口 `invoke_social_agent(asset)`，供 CIO 调用
- `app/social/nlp_tools.py` — 基于 LLM 的 NLP 工具，用于情绪分析
- `app/social/generate_report.py` — 社交情绪报告生成
- `app/social/export_tools.py` — JSON 报告持久化

### 机器学习与量化分析
- `app/ml/model_trainer.py` — LightGBM 模型训练，支持时间序列交叉验证
- `app/ml/feature_engine.py` — 特征工程管道
- `app/ml/features.py` — 技术指标特征
- `app/ml/shap_explainer.py` — 基于 SHAP 的模型可解释性
- `app/ml/generate_report.py` — 机器学习预测报告生成

### RAG 与事件记忆
- `app/rag/build_event_memory.py` — 构建 ChromaDB 事件记忆
- `app/rag/rag_tools.py` — RAG 查询工具
- `app/database/schema.py` — SQLite 数据库模式，用于新闻存储

### 新闻情报管道
- `app/pipeline/layer0.py` — 基于规则的新闻过滤（25-35% 拒绝率）
- `app/pipeline/layer1.py` — 基于 LLM 的相关性评分
- `app/pipeline/alignment.py` — 新闻-事件对齐
- `app/news/generate_report.py` — 新闻情绪报告生成

### 外部数据源
- `app/polygon/client.py` — Polygon.io API 客户端
- `app/polymarket/client.py` — Polymarket API 客户端
- `app/polymarket/tools.py` — Polymarket 预测市场工具

### 报告与输出
- `app/reporting/run_context.py` — 报告运行上下文管理
- `app/reporting/writer.py` — JSON/Markdown 报告写入器
- `app/quant/generate_report.py` — 量化分析报告生成
- `data/reports/` — 生成的报告目录
- `data/finance_data.db` — SQLite 数据库，存储新闻和事件

### 脚本与工具
- `scripts/manual_run.py` — 交互式 CLI
- `scripts/batch_process.py` — 批量股票处理
- `scripts/daily_harvester.py` — 自动化每日新闻收集
- `scripts/build_event_memory_batch.py` — 批量事件记忆构建器
- `scripts/query_event_memory.py` — 事件记忆查询工具
- `scripts/run_ml_quant_metrics.py` — 机器学习模型评估
- `scripts/explore_polymarket.py` — Polymarket 数据探索器
- `scripts/process_layer1.py` — 新闻过滤管道
- `scripts/start_mcp_servers.sh` — 启动所有 MCP 服务器
- `scripts/stop_mcp_servers.sh` — 停止所有 MCP 服务器

### 测试
- `tests/test_multi_agent_graph.py` — 多智能体图测试
- `tests/test_social_reddit_ingest.py` — Reddit 抓取测试
- `tests/test_rag_memory.py` — RAG 记忆测试
- `tests/test_polymarket_integration.py` — Polymarket 集成测试

## 架构概览

```
用户查询
    ↓
┌─────────────────────────────────────┐
│   多智能体编排器（CIO）              │
└─────────────────────────────────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │ Quant  │  │  News  │  │ Social │
    │ 智能体 │  │ 智能体 │  │ 智能体 │
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │  MCP   │  │  MCP   │  │ Reddit │
    │ 市场   │  │  新闻  │  │  API   │
    │ 数据   │  │ 搜索   │  │        │
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │yfinance│  │Tavily/ │  │  NLP   │
    │        │  │DuckDuck│  │  分析  │
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌─────────────────────────────────┐
    │   机器学习模型 & RAG 记忆        │
    │  (LightGBM, ChromaDB, SHAP)     │
    └─────────────────────────────────┘
                    ↓
            最终投资决策
```

## 数据流

1. **用户查询** → 多智能体编排器
2. **并行执行**：
   - Quant 智能体：获取市场数据、计算指标、运行机器学习模型
   - News 智能体：搜索新闻、过滤相关性、分析情绪
   - Social 智能体：抓取 Reddit、执行 NLP、生成情绪报告
3. **CIO 汇总**：将所有报告合成为最终建议
4. **输出**：结构化 JSON/Markdown 报告，包含交易信号

## 贡献

欢迎贡献！请随时提交 Pull Request。

## License

以仓库默认说明为准。
