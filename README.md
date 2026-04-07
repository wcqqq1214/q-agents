# Q-Agents

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md)

---

A multi-agent financial analysis system built with Python 3.13, LangChain, and LangGraph. Uses a Fan-out / Fan-in topology — Quant, News, and Social agents run in parallel, then a CIO agent synthesizes a final investment recommendation.

## References

This project references and is inspired by the following open-source projects:

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [owengetinfo-design/PokieTicker](https://github.com/owengetinfo-design/PokieTicker)

## Features

- **Multi-Agent Architecture**: Parallel Quant / News / Social agents with CIO synthesis
- **Market Data**: Real-time quotes and historical data with technical indicators (SMA, MACD, Bollinger Bands)
- **News Intelligence**: Multi-source aggregation (DuckDuckGo, Tavily) with sentiment analysis
- **Social Sentiment**: Reddit discussion analysis for retail investor sentiment
- **ML Predictions**: LightGBM models with SHAP explainability and time-series cross-validation
- **Event Memory (RAG)**: ChromaDB-powered semantic search over historical market events
- **Daily Digest Email**: Scheduled 3-part email with technical overview, macro news, and CIO summary

## Tech Stack

- **Language**: Python 3.13
- **AI Frameworks**: `langchain`, `langgraph`, `langchain-anthropic`, `langchain-openai`
- **ML / Data**: `pandas`, `numpy`, `lightgbm`, `shap`, `scikit-learn`, `pandas-ta`
- **Data Sources**: `yfinance`, `tavily-python`, `ddgs` (DuckDuckGo) — all via MCP servers
- **Vector DB**: `chromadb`, `langchain-chroma`
- **Config**: `python-dotenv`

## Quick Start

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- [pnpm](https://pnpm.io/) (for frontend)

### 1. Clone and enter the repo

```bash
git clone <your-repo-url>
cd q-agents
```

### 2. Install dependencies

```bash
uv sync
cd frontend && pnpm install && cd ..
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

| Key | Source | Required |
|-----|--------|----------|
| `CLAUDE_API_KEY` | [Anthropic Console](https://console.anthropic.com/) | Yes |
| `OPENAI_API_KEY` | [OpenAI Platform](https://platform.openai.com/) | Yes (embeddings) |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) | Yes |
| `POLYGON_API_KEY` | [Polygon.io](https://polygon.io/) | Optional |

Optional settings: `LLM_PROVIDER` (`claude` / `openai`, default `claude`), `LLM_TEMPERATURE` (default `0.0`), `EMBEDDING_PROVIDER` (default `openai`).

### 4. Start all services

```bash
bash scripts/startup/start_all.sh
```

This starts:
- MCP servers (ports 8000, 8001)
- FastAPI backend (port 8080)
- Next.js frontend (port 3000)

To stop everything:

```bash
bash scripts/startup/stop_all.sh
```

## Usage

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8080 |
| API Docs (Swagger) | http://localhost:8080/docs |

Submit a stock analysis query through the web UI. Results stream in real time via SSE and are saved to `data/reports/{run_id}_{asset}/`.

### Optional: Daily Digest Email

Set `DAILY_DIGEST_ENABLED=true` in `.env` to enable a scheduled email. The default watchlist is Magnificent Seven + `BTC` + `ETH`, and each run is saved to `data/reports/digests/<run_id>/`.
You can use [Resend](https://resend.com/) as the email delivery provider and fill its SMTP credentials into the settings below.

Core settings:
- `DAILY_DIGEST_TIME`, `DAILY_DIGEST_TIMEZONE`
- `DAILY_DIGEST_RECIPIENTS`, `DAILY_DIGEST_FROM`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`

## Scripts Reference

### Startup (`scripts/startup/`)

| Script | Description |
|--------|-------------|
| `start_all.sh` | Start MCP servers + API + frontend |
| `stop_all.sh` | Stop all services |
| `start_mcp_servers.sh` | Start MCP servers only (ports 8000, 8001) |
| `stop_mcp_servers.sh` | Stop MCP servers |
| `start_api.sh` | Start FastAPI backend (port 8080) |
| `start_frontend.sh` | Start Next.js frontend (port 3000) |

### ML (`scripts/ml/`)

| Script | Description |
|--------|-------------|
| `run_ml_quant_metrics.py` | Train and evaluate LightGBM models |
| `batch_process.py` | Batch analysis across multiple tickers |
| `process_layer1.py` | Run LLM-based news relevance filtering |

### RAG (`scripts/rag/`)

| Script | Description |
|--------|-------------|
| `build_event_memory_batch.py` | Build ChromaDB event memory for tickers |
| `query_event_memory.py` | Query event memory with semantic search |
| `export_events.py` | Export events to JSON |
| `list_tickers.py` | List tickers in event memory |

### Data (`scripts/data/`)

| Script | Description |
|--------|-------------|
| `download_stock_data.py` | Download historical stock OHLC data |
| `download_crypto_data.py` | Download historical crypto OHLC data |
| `daily_harvester.py` | Automated daily news collection |

### Utils (`scripts/utils/`)

| Script | Description |
|--------|-------------|
| `manual_run.py` | Interactive CLI for agent queries |
| `test_dataflows.py` | Test data provider connections |

## MCP Servers

Market data and news search are exposed via MCP servers rather than called directly.

**Market Data Server** (`mcp_servers/market_data/`) — port 8000
- Tools: `get_us_stock_quote`, `get_stock_data` (with SMA, MACD, Bollinger Bands)

**News Search Server** (`mcp_servers/news_search/`) — port 8001
- Tools: `search_news_with_duckduckgo`, `search_news_with_tavily`

If servers run at non-default addresses, set in `.env`:

```bash
MCP_MARKET_DATA_URL=http://127.0.0.1:8000/mcp
MCP_NEWS_SEARCH_URL=http://127.0.0.1:8001/mcp
```

**Troubleshooting:**

```bash
# Port in use
lsof -i :8000
kill <PID>

# Check running servers
ps aux | grep mcp_servers
```

## Project Layout

### Core Agent System
- `app/graph_multi.py` — Multi-agent LangGraph orchestration (Fan-out/Fan-in)
- `app/state.py` — AgentState for multi-agent communication
- `app/llm_config.py` — LLM provider configuration (Claude / OpenAI)
- `app/embedding_config.py` — Embedding model configuration

### Tools & Data Sources
- `app/tools/finance_tools.py` — LangChain tools (quotes, historical data, news via MCP)
- `app/tools/enhanced_tools.py` — Enhanced tools with additional functionality
- `app/tools/quant_tool.py` — Quantitative analysis tools
- `app/mcp_client/finance_client.py` — MCP client

### MCP Servers
- `mcp_servers/market_data/` — Market data server (yfinance wrapper)
- `mcp_servers/news_search/` — News search server (DuckDuckGo + Tavily)

### FastAPI Backend
- `app/api/main.py` — Application entry point
- `app/api/routes/analyze.py` — Analysis endpoints
- `app/api/routes/stocks.py` — Stock data endpoints
- `app/api/routes/crypto.py` — Cryptocurrency endpoints
- `app/api/routes/history.py` — Agent execution history
- `app/api/routes/okx.py` — OKX exchange integration
- `app/database/` — SQLite schema, agent history, OHLC storage

### Machine Learning & Quant
- `app/ml/model_trainer.py` — LightGBM training with time-series CV
- `app/ml/feature_engine.py` — Feature engineering pipeline
- `app/ml/features.py` — Technical indicator features
- `app/ml/shap_explainer.py` — SHAP explainability
- `app/ml/generate_report.py` — ML prediction reports

### RAG & Event Memory
- `app/rag/build_event_memory.py` — Build ChromaDB event memory
- `app/rag/rag_tools.py` — RAG query tools

### Report Generation
- `app/reporting/run_context.py` — Report run context
- `app/reporting/writer.py` — JSON/Markdown writers
- `app/quant/generate_report.py` — Quant analysis reports
- `app/news/generate_report.py` — News sentiment reports
- `app/social/generate_report.py` — Social sentiment reports

### Frontend (Next.js)
- `frontend/src/app/` — Next.js app directory
- `frontend/src/components/` — React components
- `frontend/tsconfig.json` — TypeScript strict mode enabled
- `frontend/eslint.config.mjs` — ESLint with TypeScript rules (no explicit `any`)

## Architecture

```
User Query
    ↓
┌─────────────────────────────────────┐
│   Multi-Agent Orchestrator (CIO)   │
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
         ↓           ↓           ↓
    ┌─────────────────────────────────┐
    │      ML Models & RAG Memory     │
    │  (LightGBM, ChromaDB, SHAP)     │
    └─────────────────────────────────┘
                    ↓
         Final Investment Decision
```

Quant, News, and Social agents execute in parallel. Each produces a structured report. The CIO agent synthesizes all three into a final recommendation saved to `data/reports/{run_id}_{asset}/`.

## Code Quality

### Backend (Python)

Uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (configured in `pyproject.toml`): line length 100, Python 3.13, rules E/F/I/N/B.

```bash
uv run ruff format .          # format
uv run ruff check --fix .     # lint + autofix
uv run pytest tests/          # tests
```

### Frontend (TypeScript)

- **TypeScript Strict Mode**: Enabled in `tsconfig.json` for type safety
- **ESLint**: Configured with Next.js and TypeScript rules
  - Enforces `@typescript-eslint/no-explicit-any` (error level)
  - Uses `eslint-config-next` for Next.js best practices

```bash
cd frontend
pnpm lint                     # run ESLint
pnpm lint:fix                 # auto-fix ESLint issues
pnpm type-check               # TypeScript type checking
```

## Contributing

### Backend
1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `uv run pytest tests/`

### Frontend
1. `cd frontend && pnpm lint:fix`
2. `pnpm type-check`
3. Ensure TypeScript strict mode compliance (no `any` types)

Submit a Pull Request after all checks pass.

## License

See repository defaults.
