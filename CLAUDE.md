# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
bash scripts/start_all.sh

# Stop everything
bash scripts/stop_all.sh
```

### Individual Services
```bash
# Start MCP servers (required for agents)
bash scripts/start_mcp_servers.sh

# Start FastAPI backend
bash scripts/start_api.sh

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

### Interactive Agent CLI
```bash
# Interactive command-line interface
uv run python -m scripts.manual_run
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
- `frontend/CLAUDE.md` - Frontend-specific instructions
- `frontend/AGENTS.md` - Next.js version warnings


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
1. Read `frontend/CLAUDE.md` and `frontend/AGENTS.md` first
2. Follow Next.js 16+ conventions (breaking changes from older versions)
3. Use shadcn/ui components from `frontend/src/components/ui/`
4. API calls go to `http://localhost:8080/api/`


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
bash scripts/stop_mcp_servers.sh
bash scripts/start_mcp_servers.sh
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
uv run python scripts/build_event_memory_batch.py
```

### Train ML Model
```bash
uv run python scripts/run_ml_quant_metrics.py
```

### Download Crypto Historical Data
```bash
uv run python scripts/download_crypto_data.py
```

### Check API Health
```bash
curl http://localhost:8080/health
```

### View API Documentation
Open http://localhost:8080/docs in browser (FastAPI auto-generated docs)

