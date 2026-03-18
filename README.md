# finance-agent

[English](README.md) | [中文](README.zh-CN.md)

---

A multi-agent financial analysis system built with Python 3.13, LangChain, and LangGraph. It uses a Fan-out / Fan-in topology (Quant + News in parallel, then CIO synthesis) to answer questions about market data and related news via MiniMax (OpenAI-compatible API) and an MCP server. A separate Social Agent ingests Reddit discussions to produce structured retail sentiment reports.

## Tech stack

- **Language**: Python 3.13
- **Frameworks**: `langchain`, `langgraph`, `langchain-openai`
- **Data**: `pandas`, `yfinance`, `ddgs` (DuckDuckGo) — all via MCP server
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
- **CLAUDE_API_KEY**: Get from [Anthropic Console](https://console.anthropic.com/)
- **OPENAI_API_KEY**: Get from [OpenAI Platform](https://platform.openai.com/) (for embeddings)
- **POLYGON_API_KEY**: Get from [Polygon.io](https://polygon.io/)
- **TAVILY_API_KEY**: Get from [Tavily](https://tavily.com/)

**Optional Configuration:**
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

Interactive CLI (recommended for quick testing):

```bash
uv run python -m tests.manual_run
```

Then type questions in natural language (e.g. “帮我看一下 AAPL 的最新股价和最近重要新闻”). Type `exit` or `quit` to exit.

One-shot from Python:

```python
from app.graph_multi import run_once
final_state = run_once("Analyze NVDA and BTC-USD")
print(final_state["final_decision"])
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

## Project layout

- `app/graph_multi.py` — Multi-agent LangGraph (Quant + News parallel, then CIO synthesis).
- `app/state.py` — `AgentState` for the multi-agent graph.
- `app/tools/finance_tools.py` — LangChain tools (all via MCP): `get_us_stock_quote`, `get_stock_data`, `search_news_with_duckduckgo`.
- `app/mcp_client/finance_client.py` — MCP client that calls the MCP servers.
- `mcp_servers/market_data/` — Market data MCP server exposing `get_us_stock_quote`, `get_stock_data` (history + indicators).
- `mcp_servers/news_search/` — News search MCP server exposing `search_news_with_duckduckgo`, `search_news_with_tavily`.
- `tests/manual_run.py` — Interactive CLI for the agent.
- `app/social/graph_social.py` — Social Agent LangGraph: Reddit ingestion → NLP → report export (used by CIO, not end users directly).
- `app/social/entrypoint.py` — `invoke_social_agent(asset)` entrypoint returning a structured social sentiment report for CIO/orchestrators.
- `app/social/nlp_tools.py` — LLM-driven NLP tools that convert Reddit text into structured sentiment/keywords/summary.
- `app/social/reddit/tools.py` — Reddit ingestion tools that fetch and clean discussion text.
- `app/social/export_tools.py` — Helpers to build and persist JSON social reports under `reports/`.
- `reports/` — JSON reports generated by the Social Agent (e.g., Reddit sentiment snapshots).
- `tests/test_social_reddit_ingest.py` — Tests for Reddit ingestion/cleaning pipeline.

## License

See repository defaults.
