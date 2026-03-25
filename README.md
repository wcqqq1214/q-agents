# finance-agent

[English](README.md) | [中文](README.zh-CN.md)

---

A multi-agent financial analysis system built with Python 3.13, LangChain, and LangGraph. It uses a Fan-out / Fan-in topology (Quant + News in parallel, then CIO synthesis) to answer questions about market data and related news via Claude/OpenAI and MCP servers. A separate Social Agent ingests Reddit discussions to produce structured retail sentiment reports.

## Features

- **Multi-Agent Architecture**: Parallel execution of Quant and News agents with CIO synthesis
- **Market Data Analysis**: Real-time quotes, historical data with technical indicators (SMA, MACD, Bollinger Bands)
- **News Intelligence**: Multi-source news aggregation (DuckDuckGo, Tavily) with sentiment analysis
- **Social Sentiment**: Reddit discussion analysis for retail investor sentiment
- **ML-Powered Predictions**: LightGBM-based quantitative models with SHAP explainability
- **Event Memory (RAG)**: ChromaDB-powered event database for historical context
- **Prediction Markets**: Polymarket integration for market sentiment signals
- **Smart News Filtering**: Two-layer filtering (rule-based + LLM) to reduce noise
- **Automated Reporting**: Structured JSON/Markdown reports with multi-language support

## Tech stack

- **Language**: Python 3.13
- **AI Frameworks**: `langchain`, `langgraph`, `langchain-anthropic`, `langchain-openai`
- **ML/Data**: `pandas`, `numpy`, `lightgbm`, `shap`, `scikit-learn`, `pandas-ta`
- **Data Sources**: `yfinance`, `tavily-python`, `ddgs` (DuckDuckGo) — all via MCP servers
- **Vector DB**: `chromadb`, `langchain-chroma`
- **Config**: `python-dotenv`

## Environment setup

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`

### 1. Clone and enter the repo

```bash
git clone <your-repo-url>
cd finance-agent
```

### 2. Create and activate a virtual environment

**With uv:**

```bash
uv venv
source .venv/bin/activate   # Linux / macOS
# or  .venv\Scripts\activate  on Windows
```

**With standard Python:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

**With uv (from project root):**

```bash
uv sync
```

**With pip:**

```bash
pip install -e .
```

Or install from `pyproject.toml` dependencies manually if not using `pip install -e .`.

### 4. Configure environment variables

Copy the environment variable template and fill in your API keys:

```bash
cp .env.example .env
```

Then edit the `.env` file and add your API keys:

**Required API Keys:**
- **CLAUDE_API_KEY**: Get from [Anthropic Console](https://console.anthropic.com/) - Primary LLM for agents
- **OPENAI_API_KEY**: Get from [OpenAI Platform](https://platform.openai.com/) - For embeddings (text-embedding-3-small)
- **POLYGON_API_KEY**: Get from [Polygon.io](https://polygon.io/) - For financial data
- **TAVILY_API_KEY**: Get from [Tavily](https://tavily.com/) - For news search

**Optional Configuration:**
- **LLM_PROVIDER**: Choose between `claude` (default) or `openai`
- **LLM_TEMPERATURE**: Control response randomness (default: 0.0)
- **EMBEDDING_PROVIDER**: Choose embedding provider (default: `openai`)
- MCP server addresses (use defaults if running locally)
- MiniMax API (alternative LLM provider)

The `.env.example` file contains all available configuration options with placeholder values.

### 5. MCP server (required for market data and news)

Market data (quotes and historical+indicators) and news search fetch data via MCP servers instead of calling yfinance or DuckDuckGo directly. You must start the MCP servers before running the agent.

**Terminal 1 — start the MCP servers:**

```bash
# Start all MCP servers (market data + news search)
bash scripts/start_mcp_servers.sh
```

Market data server listens at `http://127.0.0.1:8000/mcp` by default, news search server at `http://127.0.0.1:8001/mcp`.

**Terminal 2 — if the servers run elsewhere, set the client URLs in `.env`:**

```bash
MCP_MARKET_DATA_URL=http://127.0.0.1:8000/mcp
MCP_NEWS_SEARCH_URL=http://127.0.0.1:8001/mcp
```

## Run the agent

### Interactive CLI (recommended for quick testing)

```bash
uv run python -m scripts.manual_run
```

Then type questions in natural language:
- English: “Analyze AAPL stock with latest news”
- Chinese: “帮我看一下 AAPL 的最新股价和最近重要新闻”

Type `exit` or `quit` to exit.

### One-shot from Python

```python
from app.graph_multi import run_once
final_state = run_once(“Analyze NVDA and BTC-USD”)
print(final_state[“final_decision”])
```

### Batch Processing

Process multiple tickers in batch:

```bash
uv run python scripts/batch_process.py
```

### Daily Harvester

Automated daily news collection and analysis:

```bash
uv run python scripts/daily_harvester.py
```

## Web Frontend & API

The project includes a complete web application stack:

### Backend (FastAPI)

A REST API server providing:
- **Analysis Endpoints**: Submit queries and retrieve reports
- **Stock Data**: Real-time quotes and historical data
- **Cryptocurrency**: Crypto market data and OKX exchange integration
- **Agent History**: Query past analysis runs and tool usage
- **Health Monitoring**: Check system and MCP server status

### Frontend (Next.js)

Modern web interface with:
- **Interactive Query Interface**: Submit stock analysis requests through a web UI
- **Report Dashboard**: Browse and view generated analysis reports
- **System Monitoring**: Check the health of backend services and MCP servers
- **Real-time Updates**: Stream analysis progress via Server-Sent Events (SSE)

### Quick Start

**Option 1: Start all services at once (recommended)**

```bash
bash scripts/start_all.sh
```

This will start:
- MCP servers (ports 8000, 8001)
- FastAPI backend (port 8080)
- Next.js frontend (port 3000)

**Option 2: Start services individually**

```bash
# Terminal 1: MCP servers
bash scripts/start_mcp_servers.sh

# Terminal 2: FastAPI backend
bash scripts/start_api.sh

# Terminal 3: Frontend
cd frontend && pnpm dev
```

### Access the Application

- **Frontend**: http://localhost:3000
- **API**: http://localhost:8080
- **API Documentation**: http://localhost:8080/docs (Swagger UI)

### Frontend Development

The frontend is located in the `frontend/` directory:

```bash
cd frontend

# Install dependencies (first time only)
pnpm install

# Start development server
pnpm dev

# Build for production
pnpm build

# Start production server
pnpm start
```

### Environment Configuration

Frontend environment variables are configured in `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8080
```

## Verify tools (optional)

Market data and news tools (requires MCP server running):

```bash
uv run python -c "from app.tools.finance_tools import get_us_stock_quote; from pprint import pprint; pprint(get_us_stock_quote.invoke({'ticker': 'AAPL'}))"
```

News search:

```bash
uv run python -c "from app.tools.finance_tools import search_news_with_duckduckgo; from pprint import pprint; pprint(search_news_with_duckduckgo.invoke({'query': 'AAPL', 'limit': 2}))"
```

Historical + indicators (SMA/MACD/Bollinger) via MCP:

```bash
uv run python -c "from app.tools.finance_tools import get_stock_data; print(get_stock_data.invoke({'ticker': 'NVDA', 'period': '3mo'}))"
```

## MCP Servers

The system uses Model Context Protocol (MCP) servers to expose financial data and news search capabilities.

### Architecture

**Market Data Server** (`mcp_servers/market_data/`)
- Port: 8000
- Tools: `get_us_stock_quote`, `get_stock_data` (with SMA, MACD, Bollinger Bands)
- Dependencies: yfinance, pandas

**News Search Server** (`mcp_servers/news_search/`)
- Port: 8001
- Tools: `search_news_with_duckduckgo`, `search_news_with_tavily`
- Dependencies: ddgs, tavily-python

### Server Management

Start all servers:
```bash
bash scripts/start_mcp_servers.sh
```

Stop all servers:
```bash
bash scripts/stop_mcp_servers.sh
```

Start individual servers:
```bash
# Market Data
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/market_data/main.py

# News Search
PYTHONPATH=/home/wcqqq21/finance-agent uv run python mcp_servers/news_search/main.py
```

### Troubleshooting

**Port already in use:**
```bash
lsof -i :8000  # or :8001
kill <PID>
```

**Server not responding:**
```bash
ps aux | grep mcp_servers
```

**Tavily API key missing:**
Get an API key from https://tavily.com and add to `.env`: `TAVILY_API_KEY=your_key_here`

## Advanced Features

### Machine Learning Quantitative Analysis

Train and evaluate LightGBM models for price prediction:

```bash
uv run python scripts/run_ml_quant_metrics.py
```

Features include:
- Technical indicators (SMA, MACD, RSI, Bollinger Bands, ATR)
- Volume analysis
- SHAP explainability for model interpretability
- Time-series cross-validation

### Event Memory (RAG)

Build and query event memory database:

```bash
# Build event memory for specific tickers
uv run python scripts/build_event_memory_batch.py

# Query event memory
uv run python scripts/query_event_memory.py

# Inspect event memory
uv run python scripts/inspect_event_memory.py
```

The system uses ChromaDB to store and retrieve historical events with semantic search.

### Polymarket Integration

Explore prediction markets for sentiment signals:

```bash
# Explore Polymarket data
uv run python scripts/explore_polymarket.py

# Search by category
uv run python scripts/search_polymarket_by_category.py
```

### Smart News Filtering

Two-layer filtering pipeline:
- **Layer 0**: Rule-based filter (free, instant) - filters ~25-35% of irrelevant news
- **Layer 1**: LLM-based relevance scoring - deep semantic analysis

Process news through the pipeline:

```bash
uv run python scripts/process_layer1.py
```

### Agent Decision History

The system records complete decision-making processes for analysis and learning:

**Query decision history:**

```bash
# View recent analysis runs
curl http://localhost:8080/api/analysis-runs?limit=10

# Get detailed run information
curl http://localhost:8080/api/analysis-runs/20260321_143052

# Query tool usage statistics
curl http://localhost:8080/api/tool-calls/stats
```

**Database location:** `data/agent_history.db`

**Features:**
- Complete agent reasoning history (OpenAI standard message format)
- Tool call tracking with success/failure status
- Query APIs for analysis and debugging
- Foundation for future learning mechanisms

**Test the system:**

```bash
PYTHONPATH=/home/wcqqq21/finance-agent uv run python scripts/test_agent_history.py
```

## Project layout

### Core Agent System
- `app/graph_multi.py` — Multi-agent LangGraph orchestration (Fan-out/Fan-in)
- `app/state.py` — AgentState definition for multi-agent communication
- `app/llm_config.py` — LLM configuration (Claude/OpenAI provider selection)
- `app/embedding_config.py` — Embedding model configuration

### Tools & Data Sources
- `app/tools/finance_tools.py` — LangChain tools (all via MCP): quotes, historical data, news
- `app/tools/enhanced_tools.py` — Enhanced tools with additional functionality
- `app/tools/quant_tool.py` — Quantitative analysis tools
- `app/mcp_client/finance_client.py` — MCP client for calling MCP servers

### MCP Servers
- `mcp_servers/market_data/` — Market data MCP server (yfinance wrapper)
  - `main.py` — Server entry point
  - `indicators.py` — Technical indicators (SMA, MACD, Bollinger Bands)
- `mcp_servers/news_search/` — News search MCP server
  - `main.py` — Server entry point
  - `duckduckgo_impl.py` — DuckDuckGo search implementation
  - `tavily_impl.py` — Tavily search implementation

### FastAPI Backend
- `app/api/main.py` — FastAPI application entry point with lifespan management
- `app/api/routes/` — API route handlers
  - `analyze.py` — Analysis endpoints
  - `stocks.py` — Stock data endpoints
  - `crypto.py` — Cryptocurrency endpoints
  - `history.py` — Agent execution history
  - `okx.py` — OKX exchange integration
- `app/database/` — Database layer
  - `schema.py` — SQLite schema for news/events
  - `agent_history.py` — Agent execution tracking
  - `ohlc.py` — OHLC data storage
  - `crypto_ohlc.py` — Crypto OHLC data

### Frontend (Next.js)
- `frontend/src/app/` — Next.js app directory
- `frontend/src/components/` — React components
- `frontend/CLAUDE.md` — Frontend-specific instructions
- `frontend/AGENTS.md` — Next.js version warnings

### Machine Learning & Quant
- `app/ml/model_trainer.py` — LightGBM model training with time-series CV
- `app/ml/feature_engine.py` — Feature engineering pipeline
- `app/ml/features.py` — Technical indicator features
- `app/ml/shap_explainer.py` — SHAP-based model explainability
- `app/ml/generate_report.py` — ML prediction report generation

### RAG & Event Memory
- `app/rag/build_event_memory.py` — Build ChromaDB event memory
- `app/rag/rag_tools.py` — RAG query tools
- `app/database/schema.py` — SQLite schema for news storage

### Report Generation
- `app/reporting/run_context.py` — Report run context management
- `app/reporting/writer.py` — JSON/Markdown report writers
- `app/quant/generate_report.py` — Quantitative analysis reports
- `app/news/generate_report.py` — News sentiment reports
- `app/social/generate_report.py` — Social sentiment reports

### Frontend (Next.js)
- `frontend/src/app/` — Next.js app directory
- `frontend/src/components/` — React components
- `frontend/CLAUDE.md` — Frontend-specific instructions
- `frontend/AGENTS.md` — Next.js version warnings

## Architecture Overview

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
    ┌────────┐  ┌────────┐  ┌────────┐
    │yfinance│  │Tavily/ │  │  NLP   │
    │        │  │DuckDuck│  │Analysis│
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌─────────────────────────────────┐
    │      ML Models & RAG Memory     │
    │  (LightGBM, ChromaDB, SHAP)     │
    └─────────────────────────────────┘
                    ↓
         Final Investment Decision
```

## Data Flow

1. **User Query** → Multi-agent orchestrator
2. **Parallel Execution**:
   - Quant Agent: Fetches market data, calculates indicators, runs ML models
   - News Agent: Searches news, filters relevance, analyzes sentiment
   - Social Agent: Scrapes Reddit, performs NLP, generates sentiment report
3. **CIO Synthesis**: Combines all reports into final recommendation
4. **Output**: Structured JSON/Markdown report with trading signals

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

See repository defaults.
