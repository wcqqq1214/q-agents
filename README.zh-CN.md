# finance-agent

[English](README.md) | 中文

---

基于 Python 3.13、LangChain 与 LangGraph 的单体金融分析 Agent，通过 ReAct 图与 MiniMax（OpenAI 兼容接口）回答美股行情与相关新闻，使用 Yahoo Finance、DuckDuckGo 等工具。

## 技术栈

- **语言**: Python 3.13
- **框架**: `langchain`, `langgraph`, `langchain-openai`
- **数据**: `pandas`, `yfinance`（经 MCP 服务器）
- **搜索**: `ddgs`（DuckDuckGo）
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

在项目根目录创建 `.env` 文件（不要提交到 Git）：

```bash
# 必填：MiniMax API Key（Agent 使用 OpenAI 兼容接口）
MINIMAX_API_KEY=你的_minimax_api_key

# 可选：覆盖接口地址（默认 https://api.minimaxi.com/v1）
# MINIMAX_BASE_URL=https://api.minimax.io/v1

# 可选：模型名称（默认 MiniMax-M2.5）
# MINIMAX_MODEL=MiniMax-M2.5
```

API Key 可在 [MiniMax 开放平台](https://platform.minimaxi.com/) 获取。

### 5. MCP yfinance 服务器（行情工具必需）

行情工具通过 MCP 协议从独立服务器获取数据，不再直接调用 yfinance。运行 Agent 前需先启动 MCP 服务器。

**终端 1 — 启动 MCP 服务器：**

```bash
uv run python mcp_servers/yfinance_server/main.py
```

默认监听 `http://127.0.0.1:8000/mcp`。如需修改：

```bash
MCP_YFINANCE_HOST=0.0.0.0 MCP_YFINANCE_PORT=9000 uv run python mcp_servers/yfinance_server/main.py
```

**终端 2 — 若 MCP 服务器地址不同，在 `.env` 中配置：**

```bash
MCP_YFINANCE_URL=http://127.0.0.1:8000/mcp
```

## 运行 Agent

交互式命令行（推荐快速测试）：

```bash
uv run python -m tests.manual_run
```

按提示输入自然语言问题（例如：「帮我看一下 AAPL 的最新股价和最近重要新闻」）。输入 `exit` 或 `quit` 退出。

在 Python 中单次调用：

```python
from app.graph import run_once
messages = run_once("What is the latest price of AAPL?")
# 最后一条 AI 回复: messages[-1].content
```

## 验证工具（可选）

行情工具（需先启动 MCP 服务器）：

```bash
uv run python -c "from app.tools.finance_tools import get_us_stock_quote; from pprint import pprint; pprint(get_us_stock_quote.invoke({'ticker': 'AAPL'}))"
```

新闻搜索：

```bash
uv run python -c "from app.tools.finance_tools import search_news_with_duckduckgo; from pprint import pprint; pprint(search_news_with_duckduckgo.invoke({'query': 'AAPL', 'limit': 2}))"
```

## 项目结构

- `app/graph.py` — LangGraph ReAct 图（agent 节点 + 工具节点，MiniMax LLM）
- `app/tools/finance_tools.py` — LangChain 工具：`get_us_stock_quote`（经 MCP 调用）、`search_news_with_duckduckgo`
- `app/mcp_client/finance_client.py` — MCP 客户端，调用 yfinance MCP 服务器
- `mcp_servers/yfinance_server/main.py` — MCP 服务器，暴露 `get_us_stock_quote`（内部使用 yfinance）
- `tests/manual_run.py` — Agent 交互式 CLI

## License

以仓库默认说明为准。
