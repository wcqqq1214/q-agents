# finance-agent

[English](README.md) | [中文](README.zh-CN.md)

---

A monolithic financial analysis agent built with Python 3.13, LangChain, and LangGraph. It uses a ReAct-style graph to answer questions about US stock quotes and related news via MiniMax (OpenAI-compatible API) and tools such as Yahoo Finance and DuckDuckGo.

## Tech stack

- **Language**: Python 3.13
- **Frameworks**: `langchain`, `langgraph`, `langchain-openai`
- **Data**: `pandas`, `yfinance` (via MCP server)
- **Search**: `ddgs` (DuckDuckGo)
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

In the project root, create a `.env` file (do not commit it):

```bash
# Required: MiniMax API key (agent uses OpenAI-compatible endpoint)
MINIMAX_API_KEY=your_minimax_api_key

# Optional: override base URL (default: https://api.minimaxi.com/v1)
# MINIMAX_BASE_URL=https://api.minimax.io/v1

# Optional: model name (default: MiniMax-M2.5)
# MINIMAX_MODEL=MiniMax-M2.5
```

Get your API key from [MiniMax Open Platform](https://platform.minimaxi.com/).

### 5. MCP yfinance server (required for stock quotes)

The stock quote tool fetches data via an MCP server instead of calling yfinance directly. You must start the MCP server before running the agent.

**Terminal 1 — start the MCP server:**

```bash
uv run python mcp_servers/yfinance_server/main.py
```

By default it listens at `http://127.0.0.1:8000/mcp`. To override:

```bash
MCP_YFINANCE_HOST=0.0.0.0 MCP_YFINANCE_PORT=9000 uv run python mcp_servers/yfinance_server/main.py
```

**Terminal 2 — if the server runs elsewhere, set the client URL in `.env`:**

```bash
MCP_YFINANCE_URL=http://127.0.0.1:8000/mcp
```

## Run the agent

Interactive CLI (recommended for quick testing):

```bash
uv run python -m tests.manual_run
```

Then type questions in natural language (e.g. “帮我看一下 AAPL 的最新股价和最近重要新闻”). Type `exit` or `quit` to exit.

One-shot from Python:

```python
from app.graph import run_once
messages = run_once("What is the latest price of AAPL?")
# last AI message: messages[-1].content
```

## Verify tools (optional)

Stock quote (requires MCP server running):

```bash
uv run python -c "from app.tools.finance_tools import get_us_stock_quote; from pprint import pprint; pprint(get_us_stock_quote.invoke({'ticker': 'AAPL'}))"
```

News search:

```bash
uv run python -c "from app.tools.finance_tools import search_news_with_duckduckgo; from pprint import pprint; pprint(search_news_with_duckduckgo.invoke({'query': 'AAPL', 'limit': 2}))"
```

## Project layout

- `app/graph.py` — LangGraph ReAct graph (agent + tools nodes, MiniMax LLM).
- `app/tools/finance_tools.py` — LangChain tools: `get_us_stock_quote` (via MCP), `search_news_with_duckduckgo`.
- `app/mcp_client/finance_client.py` — MCP client that calls the yfinance MCP server.
- `mcp_servers/yfinance_server/main.py` — MCP server exposing `get_us_stock_quote` (uses yfinance).
- `tests/manual_run.py` — Interactive CLI for the agent.

## License

See repository defaults.
