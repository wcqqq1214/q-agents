# finance-agent

[English](README.md) | 中文

---

基于 Python 3.13、LangChain 与 LangGraph 的多智能体金融分析系统，采用 Fan-out / Fan-in 拓扑（Quant 与 News 并行，最后由 CIO 汇总），通过 MiniMax（OpenAI 兼容接口）与 MCP 服务器获取行情/指标与新闻并生成报告。同时，独立的 Social Agent 会抓取 Reddit 讨论并生成结构化的散户情绪报告。

## 技术栈

- **语言**: Python 3.13
- **框架**: `langchain`, `langgraph`, `langchain-openai`
- **数据**: `pandas`, `yfinance`, `ddgs`（DuckDuckGo）— 均经 MCP 服务器
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

### 5. MCP 服务器（行情/指标与新闻工具必需）

行情（含历史+指标）与新闻工具均通过 MCP 协议从独立服务器获取数据，不再直接调用 yfinance 或 DuckDuckGo。运行 Agent 前需先启动 MCP 服务器。

**终端 1 — 启动 MCP 服务器：**

```bash
uv run python mcp_servers/market_server/main.py
```

默认监听 `http://127.0.0.1:8000/mcp`。如需修改：

```bash
MCP_YFINANCE_HOST=0.0.0.0 MCP_YFINANCE_PORT=9000 uv run python mcp_servers/market_server/main.py
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
from app.graph_multi import run_once
final_state = run_once("分析 NVDA 与 BTC-USD")
print(final_state["final_decision"])
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

## 项目结构

- `app/graph_multi.py` — 多智能体 LangGraph（Quant + News 并行，CIO 汇总）
- `app/state.py` — 多智能体图使用的 `AgentState`
- `app/tools/finance_tools.py` — LangChain 工具（均经 MCP）：`get_us_stock_quote`、`get_stock_data`、`search_news_with_duckduckgo`
- `app/mcp_client/finance_client.py` — MCP 客户端，调用 yfinance MCP 服务器
- `mcp_servers/market_server/main.py` — MCP 服务器，暴露 `get_us_stock_quote`、`get_stock_data`（历史+指标）与 `search_news_with_duckduckgo`（DuckDuckGo）
- `tests/manual_run.py` — Agent 交互式 CLI
- `app/social/graph_social.py` — Social Agent 的 LangGraph：Reddit 抓取 → NLP 分析 → 报告导出（仅供 CIO/上游编排调用，不与终端用户对话）
- `app/social/entrypoint.py` — 对外入口 `invoke_social_agent(asset)`，返回给 CIO/编排层使用的结构化散户情绪报告
- `app/social/nlp_tools.py` — 基于 LLM 的 NLP 工具，将 Reddit 文本转为结构化的情绪/关键词/摘要
- `app/social/reddit/tools.py` — Reddit 抓取与清洗工具，用于获取讨论语料
- `app/social/export_tools.py` — 构建与持久化 JSON 形式 Social 报告的工具（输出到 `reports/` 目录）
- `reports/` — Social Agent 生成的 JSON 报告（例如 Reddit 情绪快照）
- `tests/test_social_reddit_ingest.py` — Reddit 抓取/清洗链路的测试

## License

以仓库默认说明为准。
