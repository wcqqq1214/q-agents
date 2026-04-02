# Q-Agents

[English](README.md) | 中文 | [日本語](README.ja.md)

---

基于 Python 3.13、LangChain 与 LangGraph 的多智能体金融分析系统。采用 Fan-out / Fan-in 拓扑：Quant、News、Social 三个智能体并行执行，最终由 CIO 智能体汇总生成投资建议。仓库同时包含 FastAPI 后端、Next.js 前端、按次运行归档的报告产物，以及可选的 Redis / ARQ 后台任务支持。

## 功能特性

- **多智能体架构**: Quant / News / Social 智能体并行，CIO 汇总分析
- **股票 + 加密资产工作台**: 股票报价来自 MCP 服务，加密报价来自热缓存，并为两类资产提供 OHLC 图表接口
- **可读报告归档**: 每次运行都会在 `data/reports/{run_id}_{asset}/` 下写出 `report.json`、各智能体 JSON 以及可读 markdown
- **新闻情报**: 多源聚合（DuckDuckGo、Tavily）与情绪分析
- **社交情绪**: Reddit 讨论分析，获取散户投资者情绪
- **ML 信号治理**: LightGBM 模型，支持 SHAP 可解释性、单标的 OOS 指标与相似度感知过滤
- **事件记忆（RAG）**: ChromaDB 驱动的历史市场事件语义检索

## 技术栈

- **语言**: Python 3.13
- **AI 框架**: `langchain`, `langgraph`, `langchain-anthropic`, `langchain-openai`
- **机器学习 / 数据**: `pandas`, `numpy`, `lightgbm`, `shap`, `scikit-learn`, `pandas-ta`
- **数据源**: `yfinance`, `tavily-python`, `ddgs`（DuckDuckGo）— 均经 MCP 服务器
- **向量数据库**: `chromadb`, `langchain-chroma`
- **后端**: `fastapi`, `uvicorn`, `httpx`, `apscheduler`
- **队列 / 缓存**: `redis`, `arq`（可选）
- **前端**: Next.js 16、React 19、Tailwind CSS 4、shadcn/ui
- **配置**: `python-dotenv`

## 快速开始

### 前置要求

- Python 3.13
- [uv](https://docs.astral.sh/uv/)（推荐）或 `pip`
- [pnpm](https://pnpm.io/)（前端）

### 1. 克隆并进入仓库

```bash
git clone <你的仓库地址>
cd q-agents
```

### 2. 安装依赖

```bash
uv sync
cd frontend && pnpm install && cd ..
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入 API 密钥：

| 密钥 | 来源 | 是否必需 |
|------|------|----------|
| `CLAUDE_API_KEY` | [Anthropic Console](https://console.anthropic.com/) | 是 |
| `MINIMAX_API_KEY` | [MiniMax Platform](https://www.minimaxi.com/platform) | 是 |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) | 是 |
| `POLYGON_API_KEY` | [Polygon.io](https://polygon.io/) | 可选 |
| `OKX_DEMO_API_KEY` / `OKX_DEMO_SECRET_KEY` / `OKX_DEMO_PASSPHRASE` | OKX | 可选 |

常用可选配置：`CLAUDE_BASE_URL`、`CLAUDE_MODEL`、`MINIMAX_BASE_URL`、`MINIMAX_EMBEDDING_MODEL`、`MCP_MARKET_DATA_URL`、`MCP_NEWS_SEARCH_URL`、`USE_PROXY`、`REDIS_ENABLED`、`REDIS_URL`、`NEXT_PUBLIC_API_URL`。

设置 API/UI 里仍然保留 `OPENAI_API_KEY` 字段用于兼容，但当前 embedding 流程实际读取的是 `.env` 中的 `MINIMAX_*` 配置。

### 4. 可选：启动 Redis 后台任务依赖

```bash
docker compose up -d
```

即使 Redis 不可用，后端也会回退到进程内执行定时/后台任务。

### 5. 启动所有服务

```bash
bash scripts/startup/start_all.sh
```

将启动：
- MCP 服务器（端口 8000、8001）
- FastAPI 后端（端口 8080）
- Next.js 前端（端口 3000）

停止所有服务：

```bash
bash scripts/startup/stop_all.sh
```

## 使用方式

| 服务 | 地址 |
|------|------|
| 前端（首页） | http://localhost:3000 |
| 前端 Reports | http://localhost:3000/reports |
| 前端 System | http://localhost:3000/system |
| 前端 Settings | http://localhost:3000/settings |
| API | http://localhost:8080 |
| API 文档（Swagger）| http://localhost:8080/docs |

可在首页切换股票与加密资产观察列表、查看 OHLC 图表，并提交分析查询。分析结果通过 SSE 返回，每次完成的运行都会保存到 `data/reports/{run_id}_{asset}/`。

## 脚本参考

### 启动脚本（`scripts/startup/`）

| 脚本 | 说明 |
|------|------|
| `start_all.sh` | 启动 MCP 服务器 + API + 前端 |
| `stop_all.sh` | 停止所有服务 |
| `start_mcp_servers.sh` | 仅启动 MCP 服务器（端口 8000、8001）|
| `stop_mcp_servers.sh` | 停止 MCP 服务器 |
| `start_api.sh` | 启动 FastAPI 后端（端口 8080）|
| `start_frontend.sh` | 启动 Next.js 前端（端口 3000）|

### 机器学习（`scripts/ml/`）

| 脚本 | 说明 |
|------|------|
| `run_ml_quant_metrics.py` | 训练和评估 LightGBM 模型 |
| `compare_models.py` | 为单个标的生成 markdown ML 评估报告 |
| `batch_process.py` | 批量分析多个股票代码 |
| `process_layer1.py` | 运行 LLM 新闻相关性过滤 |

### RAG（`scripts/rag/`）

| 脚本 | 说明 |
|------|------|
| `build_event_memory_batch.py` | 为股票代码构建 ChromaDB 事件记忆 |
| `query_event_memory.py` | 语义搜索事件记忆 |
| `export_events.py` | 导出事件为 JSON |
| `list_tickers.py` | 列出事件记忆中的股票代码 |

### 数据（`scripts/data/`）

| 脚本 | 说明 |
|------|------|
| `download_stock_data.py` | 下载历史股票 OHLC 数据 |
| `download_crypto_data.py` | 下载历史加密货币 OHLC 数据 |
| `daily_harvester.py` | 自动化每日新闻采集 |

### 工具（`scripts/utils/`）

| 脚本 | 说明 |
|------|------|
| `manual_run.py` | 交互式 CLI 查询 |
| `test_dataflows.py` | 测试数据提供商连接 |

### 后台任务

```bash
uv run arq app.tasks.WorkerSettings
```

启动可选的 ARQ Worker，用于 Redis 支撑的后台任务，例如定时 OHLC 更新。

## MCP 服务器

行情与新闻工具通过 MCP 服务器暴露，而非直接调用。

**市场数据服务器**（`mcp_servers/market_data/`）— 端口 8000
- 工具：`get_us_stock_quote`、`get_stock_data`（含 SMA、MACD、布林带）

**新闻搜索服务器**（`mcp_servers/news_search/`）— 端口 8001
- 工具：`search_news_with_duckduckgo`、`search_news_with_tavily`

若服务器地址非默认，在 `.env` 中配置：

```bash
MCP_MARKET_DATA_URL=http://127.0.0.1:8000/mcp
MCP_NEWS_SEARCH_URL=http://127.0.0.1:8001/mcp
```

**故障排查：**

```bash
# 端口被占用
lsof -i :8000
kill <PID>

# 检查运行中的服务器
ps aux | grep mcp_servers
```

## 项目结构

### 核心智能体系统
- `app/graph_multi.py` — 多智能体 LangGraph 编排（Fan-out/Fan-in）
- `app/state.py` — 多智能体通信的 AgentState
- `app/llm_config.py` — LLM 提供商配置（Claude / OpenAI）
- `app/embedding_config.py` — Embedding 模型配置

### 工具与数据源
- `app/tools/finance_tools.py` — LangChain 工具（报价、历史数据、新闻，均经 MCP）
- `app/tools/enhanced_tools.py` — 增强工具
- `app/tools/quant_tool.py` — 量化分析工具
- `app/mcp_client/finance_client.py` — MCP 客户端

### MCP 服务器
- `mcp_servers/market_data/` — 市场数据服务器（yfinance 封装）
- `mcp_servers/news_search/` — 新闻搜索服务器（DuckDuckGo + Tavily）

### FastAPI 后端
- `app/api/main.py` — 应用入口
- `app/api/routes/analyze.py` — 分析端点
- `app/api/routes/reports.py` — 报告列表与详情端点
- `app/api/routes/system.py` — MCP 健康状态端点
- `app/api/routes/settings.py` — 运行时配置端点
- `app/api/routes/stocks.py` — 股票数据端点
- `app/api/routes/ohlc.py` — 股票历史 OHLC 与元数据端点
- `app/api/routes/crypto.py` — 加密货币端点
- `app/api/routes/crypto_klines.py` — 合并热/冷数据的加密 K 线端点
- `app/api/routes/history.py` — 智能体执行历史
- `app/api/routes/okx.py` — OKX 交易所集成
- `app/database/` — SQLite 模式、智能体历史、OHLC 存储

### 机器学习与量化分析
- `app/ml/model_trainer.py` — LightGBM 训练，支持时间序列交叉验证
- `app/ml/model_registry.py` — 模型编排、对比报告与评分辅助
- `app/ml/feature_engine.py` — 特征工程管道
- `app/ml/features.py` — 技术指标特征
- `app/ml/signal_filter.py` — 相似度感知的信号治理
- `app/ml/similarity.py` — 历史相似样本检索
- `app/ml/text_features.py` — 文本衍生特征
- `app/ml/shap_explainer.py` — SHAP 可解释性

### 后台任务与实时数据
- `app/services/realtime_agent.py` — 加密热缓存预热与刷新循环
- `app/tasks/update_ohlc.py` — 定时日线 OHLC 更新任务
- `app/tasks/worker_settings.py` — ARQ Worker 配置

### RAG 与事件记忆
- `app/rag/build_event_memory.py` — 构建 ChromaDB 事件记忆
- `app/rag/rag_tools.py` — RAG 查询工具

### 报告生成
- `app/reporting/run_context.py` — 报告运行上下文
- `app/reporting/writer.py` — JSON/Markdown 写入器
- `app/quant/generate_report.py` — 量化分析报告
- `app/news/generate_report.py` — 新闻情绪报告
- `app/social/generate_report.py` — 社交情绪报告

### 前端（Next.js）
- `frontend/src/app/` — Next.js 应用目录
- `frontend/src/components/` — React 组件
- `frontend/src/lib/api.ts` — 带类型的前端 API 客户端
- `frontend/tsconfig.json` — TypeScript 严格模式已启用
- `frontend/eslint.config.mjs` — ESLint 配置，含 TypeScript 规则（禁止显式 `any`）

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
    ┌─────────────────────────────────┐
    │   机器学习模型 & RAG 记忆        │
    │  (LightGBM, ChromaDB, SHAP)     │
    └─────────────────────────────────┘
                    ↓
            最终投资决策
```

Quant、News、Social 三个智能体并行执行，各自生成结构化报告。CIO 智能体汇总三份报告，生成最终建议，保存至 `data/reports/{run_id}_{asset}/`。

## 代码质量

### 后端（Python）

使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化（配置于 `pyproject.toml`）：行长度 100，Python 3.13，规则 E/F/I/N/B。

```bash
uv run ruff format .          # 格式化
uv run ruff check --fix .     # 检查 + 自动修复
uv run pytest tests/          # 测试
```

### 前端（TypeScript）

- **TypeScript 严格模式**：在 `tsconfig.json` 中启用，确保类型安全
- **ESLint**：配置了 Next.js 和 TypeScript 规则
  - 强制执行 `@typescript-eslint/no-explicit-any`（错误级别）
  - 使用 `eslint-config-next` 遵循 Next.js 最佳实践

```bash
cd frontend
pnpm lint                     # 运行 ESLint
pnpm lint:fix                 # 自动修复 ESLint 问题
pnpm type-check               # TypeScript 类型检查
```

## 更多文档

- [docs/PROXY_CONFIGURATION.md](docs/PROXY_CONFIGURATION.md) — WSL2 / Linux / macOS / Windows 代理配置
- [docs/okx-api-guide.md](docs/okx-api-guide.md) — OKX API 配置与端点说明

## 贡献

### 后端
1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `uv run pytest tests/`

### 前端
1. `cd frontend && pnpm lint:fix`
2. `pnpm type-check`
3. 确保符合 TypeScript 严格模式（禁止 `any` 类型）

所有检查通过后提交 Pull Request。

## License

以仓库默认说明为准。
