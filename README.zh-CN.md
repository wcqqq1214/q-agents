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

复制环境变量模板并填入你的 API 密钥：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件，填入你的 API 密钥：

**必需的 API 密钥：**
- **CLAUDE_API_KEY**: 从 [Anthropic Console](https://console.anthropic.com/) 获取
- **OPENAI_API_KEY**: 从 [OpenAI Platform](https://platform.openai.com/) 获取（用于 embeddings）
- **POLYGON_API_KEY**: 从 [Polygon.io](https://polygon.io/) 获取
- **TAVILY_API_KEY**: 从 [Tavily](https://tavily.com/) 获取

**可选配置：**
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

## 项目结构

- `app/graph_multi.py` — 多智能体 LangGraph（Quant + News 并行，CIO 汇总）
- `app/state.py` — 多智能体图使用的 `AgentState`
- `app/tools/finance_tools.py` — LangChain 工具（均经 MCP）：`get_us_stock_quote`、`get_stock_data`、`search_news_with_duckduckgo`
- `app/mcp_client/finance_client.py` — MCP 客户端，调用 MCP 服务器
- `mcp_servers/market_data/` — 市场数据 MCP 服务器，暴露 `get_us_stock_quote`、`get_stock_data`（历史+指标）
- `mcp_servers/news_search/` — 新闻搜索 MCP 服务器，暴露 `search_news_with_duckduckgo`、`search_news_with_tavily`
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
