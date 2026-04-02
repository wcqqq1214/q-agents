# AGENTS.md

This file provides guidance to Codex and other coding agents when working with code in this repository.

## Scope

- This root `AGENTS.md` applies to the entire repository.
- More specific instructions in subdirectories take precedence for files within those directories.
- When modifying `frontend/`, treat `frontend/AGENTS.md` as the canonical frontend rule file.
- Legacy `CLAUDE.md` files may still contain useful context, but `AGENTS.md` should be kept in sync for agent-facing instructions.

## Python Environment

This project uses **uv** for Python environment management (Python 3.13).

**CRITICAL:** Always use `uv run python` instead of `python` or `python3` when running Python commands.

Examples:
```bash
# Run Python scripts
uv run python script.py

# Run Python commands
uv run python -c "import module; print('test')"

# Run pytest
uv run pytest tests/

# Run uvicorn for API server
uv run uvicorn app.api.main:app --port 8080
```

## Quick Start Commands

### Start All Services
```bash
# Start everything (MCP servers + API + Frontend)
bash scripts/startup/start_all.sh

# Stop everything
bash scripts/startup/stop_all.sh
```

### Individual Services
```bash
# Start MCP servers (required for agents)
bash scripts/startup/start_mcp_servers.sh

# Start FastAPI backend
bash scripts/startup/start_api.sh

# Start Next.js frontend
cd frontend && pnpm dev
```

### Run Tests
```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_multi_agent_graph.py

# Run with coverage
uv run pytest --cov=app tests/
```

### Linting & Formatting (Ruff)
```bash
# Check linting errors
uv run ruff check .

# Auto-fix linting errors
uv run ruff check --fix .

# Format code
uv run ruff format .

# Check formatting without modifying
uv run ruff format --check .
```

### Interactive Agent CLI
```bash
# Interactive command-line interface
uv run python -m scripts.utils.manual_run
```


## Architecture Overview

This is a multi-agent financial analysis system with a Fan-out/Fan-in topology:

```
User Query
    ↓
┌─────────────────────────────────────┐
│   CIO Agent (Orchestrator)          │
└─────────────────────────────────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │ Quant  │  │  News  │  │ Social │
    │ Agent  │  │ Agent  │  │ Agent  │
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │  MCP   │  │  MCP   │  │ Reddit │
    │ Market │  │  News  │  │  API   │
    │  Data  │  │ Search │  │        │
    └────────┘  └────────┘  └────────┘
```

### Agent Responsibilities

- **Quant Agent**: Fetches market data, calculates technical indicators (SMA, MACD, Bollinger Bands), runs ML models
- **News Agent**: Searches news via DuckDuckGo/Tavily, filters relevance, analyzes sentiment
- **Social Agent**: Scrapes Reddit discussions, performs NLP sentiment analysis
- **CIO Agent**: Synthesizes all reports into final investment recommendation

### Key Components

- **LangGraph**: Multi-agent orchestration (`app/graph_multi.py`)
- **MCP Servers**: Model Context Protocol servers expose financial data and news search
  - Market Data Server (port 8000): yfinance wrapper with technical indicators
  - News Search Server (port 8001): DuckDuckGo and Tavily integration
- **FastAPI Backend**: REST API for frontend integration (`app/api/main.py`)
- **Next.js Frontend**: React-based UI with real-time updates

### Data Provider Abstraction Layer

**Location**: `app/dataflows/`

**Purpose**: Provider-agnostic data interface with caching and automatic fallback.

**Key Components**:
- `models.py`: Pydantic data contracts (StockCandle, NewsArticle, etc.)
- `interface.py`: DataFlowRouter with fallback logic
- `cache.py`: Redis cache layer (7d TTL for stock data, 1h for news)
- `providers/`: MCP and yfinance adapters

**Usage**:
```python
from app.dataflows.interface import DataFlowRouter
from datetime import datetime

router = DataFlowRouter()
candles = await router.get_stock_data(
    "AAPL",
    datetime(2024, 1, 1),
    datetime(2024, 12, 31)
)
```

**Configuration**:
Edit `app/dataflows/config.py` to change data vendors:
```python
"data_vendors": {
    "stock_data": "yfinance",  # Switch from MCP to yfinance
}
```

**Fallback Strategy**:
- Primary: MCP servers (localhost:8000, localhost:8001)
- Fallback: yfinance (automatic on MCP timeout/error)
- Cache: Redis (reduces API calls)


## Project Structure

### Core Agent System
- `app/graph_multi.py` - Multi-agent LangGraph orchestration (Fan-out/Fan-in)
- `app/state.py` - AgentState definition for multi-agent communication
- `app/llm_config.py` - LLM configuration (Claude/OpenAI provider selection)
- `app/embedding_config.py` - Embedding model configuration

### Tools & Data Sources
- `app/tools/finance_tools.py` - LangChain tools (all via MCP): quotes, historical data, news
- `app/tools/enhanced_tools.py` - Enhanced tools with additional functionality
- `app/tools/quant_tool.py` - Quantitative analysis tools
- `app/mcp_client/finance_client.py` - MCP client for calling MCP servers

### MCP Servers
- `mcp_servers/market_data/` - Market data MCP server (yfinance wrapper)
  - `main.py` - Server entry point
  - `indicators.py` - Technical indicators (SMA, MACD, Bollinger Bands)
- `mcp_servers/news_search/` - News search MCP server
  - `main.py` - Server entry point
  - `duckduckgo_impl.py` - DuckDuckGo search implementation
  - `tavily_impl.py` - Tavily search implementation

### FastAPI Backend
- `app/api/main.py` - FastAPI application entry point with lifespan management
- `app/api/routes/` - API route handlers
  - `analyze.py` - Analysis endpoints
  - `stocks.py` - Stock data endpoints
  - `crypto.py` - Cryptocurrency endpoints
  - `history.py` - Agent execution history
  - `okx.py` - OKX exchange integration
- `app/database/` - Database layer
  - `schema.py` - SQLite schema for news/events
  - `agent_history.py` - Agent execution tracking
  - `ohlc.py` - OHLC data storage
  - `crypto_ohlc.py` - Crypto OHLC data

### Machine Learning & Quant
- `app/ml/model_trainer.py` - LightGBM model training with time-series CV
- `app/ml/feature_engine.py` - Feature engineering pipeline
- `app/ml/features.py` - Technical indicator features
- `app/ml/shap_explainer.py` - SHAP-based model explainability
- `app/ml/generate_report.py` - ML prediction report generation

### RAG & Event Memory
- `app/rag/build_event_memory.py` - Build ChromaDB event memory
- `app/rag/rag_tools.py` - RAG query tools
- `app/database/schema.py` - SQLite schema for news storage

### Report Generation
- `app/reporting/run_context.py` - Report run context management
- `app/reporting/writer.py` - JSON/Markdown report writers
- `app/quant/generate_report.py` - Quantitative analysis reports
- `app/news/generate_report.py` - News sentiment reports
- `app/social/generate_report.py` - Social sentiment reports

### Frontend (Next.js)
- `frontend/src/app/` - Next.js app directory
- `frontend/src/components/` - React components
- `frontend/AGENTS.md` - Canonical frontend agent instructions
- `frontend/CLAUDE.md` - Legacy frontend instructions kept for compatibility
- `frontend/tsconfig.json` - TypeScript strict mode enabled
- `frontend/eslint.config.mjs` - ESLint with TypeScript rules


## Development Workflow

### Multi-Agent Graph Execution Flow

1. User submits query via CLI or API
2. `run_once()` in `app/graph_multi.py` creates a LangGraph with parallel execution:
   - Quant Agent calls MCP market data tools → generates technical report
   - News Agent calls MCP news search tools → generates sentiment report
   - Social Agent scrapes Reddit → generates retail sentiment report
3. CIO Agent receives all three reports and synthesizes final recommendation
4. Reports saved to `data/reports/{run_id}_{asset}/`

### Adding New Tools

Tools must be added to the appropriate agent's tool list:
- Quant tools: `app/tools/__init__.py` → `QUANT_TOOLS`
- News tools: `app/tools/__init__.py` → `NEWS_TOOLS`
- Tools are LangChain-compatible and typically wrap MCP client calls

### MCP Server Development

MCP servers follow the Model Context Protocol specification:
- Each server exposes tools via `/mcp` endpoint
- Tools are defined with JSON schemas
- Client calls are made via `app/mcp_client/finance_client.py`

### Database Migrations

The project uses SQLite with manual schema management:
- Schema defined in `app/database/schema.py`
- Agent history in `app/database/agent_history.py`
- OHLC data in `app/database/ohlc.py` and `app/database/crypto_ohlc.py`

### Frontend Development

When modifying `frontend/` code:
1. Read `frontend/AGENTS.md` first and treat it as canonical
2. Follow Next.js 16+ conventions (breaking changes from older versions)
3. Use shadcn/ui components from `frontend/src/components/ui/`
4. API calls go to `http://localhost:8080/api/`
5. **TypeScript Strict Mode**: All code must comply with strict type checking
6. **ESLint Rules**: No explicit `any` types allowed (`@typescript-eslint/no-explicit-any: error`)

Frontend linting and type checking:
```bash
cd frontend
pnpm lint              # Run ESLint
pnpm lint:fix          # Auto-fix ESLint issues
pnpm type-check        # TypeScript type checking
```


## Important Notes

### Python Command Prefix
**ALWAYS** use `uv run python` instead of bare `python` or `python3`. This ensures the correct virtual environment and dependencies are used.

### MCP Server Dependency
The agent system requires MCP servers to be running. If you see connection errors:
```bash
# Check if MCP servers are running
lsof -i :8000  # Market data server
lsof -i :8001  # News search server

# Restart if needed
bash scripts/startup/stop_mcp_servers.sh
bash scripts/startup/start_mcp_servers.sh
```

### Environment Variables
Required API keys in `.env`:
- `CLAUDE_API_KEY` or `OPENAI_API_KEY` - For LLM inference
- `OPENAI_API_KEY` - For embeddings (text-embedding-3-small)
- `TAVILY_API_KEY` - For news search
- `POLYGON_API_KEY` - For financial data (optional)

### Agent State Management
The `AgentState` in `app/state.py` is the single source of truth for multi-agent communication. All agents read from and write to this shared state.

### Report Output
Generated reports are saved to `data/reports/{run_id}_{asset}/`:
- `quant_report.json` - Technical analysis
- `news_report.json` - News sentiment
- `social_report.json` - Reddit sentiment
- `cio_decision.md` - Final recommendation

## Common Development Tasks

### Run a Single Analysis
```bash
uv run python -c "from app.graph_multi import run_once; print(run_once('Analyze AAPL')['final_decision'])"
```

### Build Event Memory (RAG)
```bash
uv run python scripts/rag/build_event_memory_batch.py
```

### Train ML Model
```bash
uv run python scripts/ml/run_ml_quant_metrics.py
```

### Download Crypto Historical Data
```bash
uv run python scripts/data/download_crypto_data.py
```

### Check API Health
```bash
curl http://localhost:8080/health
```

### View API Documentation
Open http://localhost:8080/docs in browser (FastAPI auto-generated docs)


## Chinese Development Guidelines (中文开发规范)

### 角色定位与项目目标
本仓库构建基于 LangGraph 的**单体金融分析 Agent 系统**，逐步扩展出：
- **News / CIO 决策 Agent**
- **RAG 历史事件记忆库（Event-Driven Fused Memory）**
- 其它围绕投资研究、风控和资产配置的子模块

目标是**持续维护一套清晰、一致、可扩展的架构与规范**。

### 技术栈与运行环境规范
- **语言**：Python 3.13（代码必须兼容 3.13）
- **核心框架**：
  - `langgraph`（使用最新语法，基于 `StateGraph` / `MessagesState`）
  - `langchain`, `langchain-openai`（或 `langchain-anthropic`）
- **数据处理**：`pandas`, `yfinance`
- **向量检索 / RAG**：`chromadb`, `langchain-chroma`
- **搜索工具**：`tavily-python` 或 `duckduckgo-search`
- **环境变量管理**：`python-dotenv`
- **包管理**：推荐使用 `uv` 或 `pip`，但需保证依赖写入 `pyproject.toml` 或 `requirements.txt`

**要求**：
1. 新增依赖时必须同步更新依赖文件（`pyproject.toml` 或 `requirements.txt`）
2. 所有需要的环境变量（如 API Key、环境配置）必须在 `.env.example` 中给出示例键名

### 代码风格与工程规范
- **Git 提交信息**：必须使用英文，推荐 conventional commits，例如：
  - `feat(rag): add event memory builder`
  - `fix(agent): handle missing ticker metadata`
- **类型提示 (Type Hinting)**：
  - 所有函数、类方法、State 定义必须有**完整、严格的类型注解**
  - 优先使用标准库类型（`list[str]` 而非 `List[str]`，除非项目统一约定）
- **Docstring 规范**：
  - 所有对外暴露函数、工具函数、LangGraph 节点处理函数必须有 **Google-style Docstring**
  - 对于 `@tool` 装饰的函数，Docstring 要**极其详细**，清晰说明：
    - 适用场景（When to use）
    - 参数语义与取值约束
    - 返回值结构
    - 典型调用示例 / 注意事项
- **错误处理**：
  - 避免静默失败，关键路径必须显式抛出自定义异常或返回带错误信息的结构
  - 与外部 API / 网络请求相关的逻辑要做好超时、重试与异常分类
- **日志与可观测性**：
  - 重要节点（如 RAG 检索结果、关键决策分支）应通过统一的 logging 记录；避免 `print`

### Agent 架构设计（LangGraph + ReAct）
本仓库的**主金融 Agent** 必须使用最新的 LangGraph 写法，遵循如下约束：

- **State 定义**：
  - 使用 `langgraph.graph.MessagesState` 作为基础 State
  - 如需扩展结构化字段（如 `positions`, `risk_limits`），应通过自定义 `TypedDict` 或 `pydantic` 模型，保持类型明确

- **必备节点（Nodes）**：
  - `agent`：
    - 绑定大模型与工具（tools）
    - 职责：解析用户意图，规划工具调用顺序（ReAct 风格），在合适时输出最终回答
  - `tools`：
    - 使用 `ToolNode` 执行工具（行情获取、新闻搜索、RAG 检索、回测等）
    - 将结果以 `ToolMessage` 形式写回 State

- **图结构（Edges）**：
  - 从 `START` → `agent`
  - 从 `agent` 出发的条件边（Conditional Edge）：
    - 若存在工具调用请求：`agent` → `tools`
    - 否则：`agent` → `END`
  - 从 `tools` → `agent`（工具执行完成后回到决策节点）

**严禁**：
- 不允许使用已废弃的 `AgentExecutor` / 旧版 LangChain Agent 模式
- 不允许在图外使用零散的"工具 + LLM 调用"代替 LangGraph 流程

### RAG 历史事件记忆库（Event-Driven Fused Memory）规范
RAG 记忆库需要严格遵循 `rag_event_memory_blueprint.md` 中的设计思想，并保证：

- **数据形态**：将"历史重大新闻文本" + "事后真实收益率"拼接为标准化的"复盘档案"文本（Fused Memory Block）
- **向量存储**：使用本地 `ChromaDB`（例如目录 `./chroma_db`），通过 `langchain-chroma` 接入
- **嵌入模型**：通过 `langchain-openai`（或兼容模型）配置 Embedding，模型名称从环境变量读取
- **Metadata 规则（极重要）**：
  - 每条 Document 必须包含：
    - `ticker`: 如 `"META"`, `"NVDA"`
    - `date`: 事件发生日期（`"YYYY-MM-DD"`）
    - `event_type`: 如 `"earnings"`, `"macro"`, `"guidance"`, `"management_change"` 等
  - RAG 检索时，必须利用 `metadata` 做过滤，例如：`filter={"ticker": "TSLA"}`

#### 构建模块（建议文件：`build_event_memory.py`）
实现以下核心函数（具体实现细节可根据项目演进微调，但语义需保持一致）：
- `fetch_post_event_returns(ticker: str, date: str) -> dict[str, float]`
- `create_memory_document(ticker: str, date: str, news_summary: str, returns: dict[str, float]) -> str`
- `init_chroma_db(docs: list[str], metadatas: list[dict[str, str]]) -> None`

要求：
- 从 `yfinance` 获取价格数据，至少计算：
  - T+1 收益率
  - T+5 累计收益率
- 输出的文本应符合蓝图中的"【历史事件复盘】"模板，方便人类和 LLM 阅读

#### 工具模块（建议文件：`rag_tools.py`）
- 使用 `@tool` 定义：
  - `search_historical_event_impact(query: str, ticker: str) -> str`
- 要点：
  - 内部通过 Chroma retriever 按 `query` 做相似度检索
  - 检索时对 `ticker` 做 metadata 过滤，避免跨资产污染
  - 返回值为可直接给 LLM 消化的长文本，包含若干历史事件复盘（Top K，一般 3 条左右）

#### 测试规范（建议文件：`tests/test_rag_memory.py`）
- 必须提供**可运行的最小样例**（可使用 Mock 数据，避免依赖真实 API 速率）
- 测试内容至少包括：
  - 构建 NVDA / META 的历史事件记忆样本
  - 调用 `search_historical_event_impact("earnings beat", "NVDA")` 类似查询时：
    - 返回内容中包含 NVDA 相关复盘
    - 不应混入 META（或其它 ticker）的事件

### 与 AI 助手的交互约定
当 Codex 或其他 AI 助手在本仓库内工作时，需要额外遵守以下约束：
- **回答语言**：默认使用中文解释思路与高层设计；代码、提交信息、函数命名等保持英文
- **重构与新增模块时**：
  - 优先保持现有架构一致性（尤其是 LangGraph State / 节点命名）
  - 为新模块增加最小可运行示例或测试（尤其是工具与 RAG 流程）
- **对现有设计有改进建议时**：
  - 可以在回答中提出更优架构，但在未得到明确指示前，避免大规模重构

### 禁止事项与注意点
- **禁止**：
  - 使用旧版 LangChain AgentExecutor 替代 LangGraph
  - 在未说明的情况下引入重量级依赖（如大型 Web 框架、数据库）导致项目膨胀
  - 在仓库中提交 `.env`、明文密钥或含有隐私数据的文件
- **注意**：
  - 对于金融相关逻辑，要在 Docstring 中明确假设前提与限制（例如"仅为教学示例，不构成投资建议"）
  - 在涉及回测或收益率展示时，标明时间区间与数据来源（如 yfinance）

---

本规则文件会随着项目演进迭代更新；在做出重大架构调整（尤其是 Agent 拓扑、RAG 设计）前，建议先在此处补充/修订约束，再进行实现。
