# Q-Agents

[English](README.md) | [中文](README.zh-CN.md) | 日本語

---

Python 3.13、LangChain、LangGraph で構築されたマルチエージェント金融分析システム。Fan-out / Fan-in トポロジーを採用 — Quant・News・Social の3エージェントが並列実行され、最終的に CIO エージェントが投資推奨をまとめます。

## 参考プロジェクト

このプロジェクトは、以下のオープンソースプロジェクトを参考にしています。

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [owengetinfo-design/PokieTicker](https://github.com/owengetinfo-design/PokieTicker)

## 機能

- **マルチエージェントアーキテクチャ**: Quant / News / Social エージェントの並列実行と CIO による統合
- **市場データ**: リアルタイム相場と履歴データ、テクニカル指標（SMA、MACD、ボリンジャーバンド）
- **ニュースインテリジェンス**: 複数ソース集約（DuckDuckGo、Tavily）とセンチメント分析
- **ソーシャルセンチメント**: Reddit ディスカッション分析による個人投資家心理の把握
- **ML 予測**: LightGBM モデル、SHAP 説明可能性、時系列クロスバリデーション
- **イベントメモリ（RAG）**: ChromaDB による過去市場イベントのセマンティック検索
- **デイリーダイジェストメール**: テクニカル概況、マクロニュース、CIO 要約の 3 部構成メールを定期配信

## 技術スタック

- **言語**: Python 3.13
- **AI フレームワーク**: `langchain`, `langgraph`, `langchain-anthropic`, `langchain-openai`
- **ML / データ**: `pandas`, `numpy`, `lightgbm`, `shap`, `scikit-learn`, `pandas-ta`
- **データソース**: `yfinance`, `tavily-python`, `ddgs`（DuckDuckGo）— すべて MCP サーバー経由
- **ベクトル DB**: `chromadb`, `langchain-chroma`
- **設定**: `python-dotenv`

## クイックスタート

### 前提条件

- Python 3.13
- [uv](https://docs.astral.sh/uv/)（推奨）または `pip`
- [pnpm](https://pnpm.io/)（フロントエンド用）

### 1. リポジトリのクローンと移動

```bash
git clone <your-repo-url>
cd q-agents
```

### 2. 依存関係のインストール

```bash
uv sync
cd frontend && pnpm install && cd ..
```

### 3. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して API キーを入力してください：

| キー | 取得先 | 必須 |
|------|--------|------|
| `CLAUDE_API_KEY` | [Anthropic Console](https://console.anthropic.com/) | 必須 |
| `OPENAI_API_KEY` | [OpenAI Platform](https://platform.openai.com/) | 必須（embeddings）|
| `TAVILY_API_KEY` | [Tavily](https://tavily.com/) | 必須 |
| `POLYGON_API_KEY` | [Polygon.io](https://polygon.io/) | 任意 |

オプション設定: `LLM_PROVIDER`（`claude` / `openai`、デフォルト `claude`）、`LLM_TEMPERATURE`（デフォルト `0.0`）、`EMBEDDING_PROVIDER`（デフォルト `openai`）。

### 4. 全サービスの起動

```bash
bash scripts/startup/start_all.sh
```

以下が起動します：
- MCP サーバー（ポート 8000、8001）
- FastAPI バックエンド（ポート 8080）
- Next.js フロントエンド（ポート 3000）

全サービスの停止：

```bash
bash scripts/startup/stop_all.sh
```

## 使い方

| サービス | URL |
|---------|-----|
| フロントエンド | http://localhost:3000 |
| API | http://localhost:8080 |
| API ドキュメント（Swagger）| http://localhost:8080/docs |

Web UI から株式分析クエリを送信してください。結果は SSE でリアルタイムにストリーミングされ、`data/reports/{run_id}_{asset}/` に保存されます。

### オプション: デイリーダイジェストメール

`.env` で `DAILY_DIGEST_ENABLED=true` を設定すると定期メールを有効化できます。デフォルトの監視対象は Magnificent Seven と `BTC`、`ETH` で、各実行結果は `data/reports/digests/<run_id>/` に保存されます。
[Resend](https://resend.com/) をメール配信プロバイダーとして利用でき、下記の SMTP 設定にその認証情報を入れれば動作します。

主な設定:
- `DAILY_DIGEST_TIME`, `DAILY_DIGEST_TIMEZONE`
- `DAILY_DIGEST_RECIPIENTS`, `DAILY_DIGEST_FROM`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`

## スクリプトリファレンス

### 起動スクリプト（`scripts/startup/`）

| スクリプト | 説明 |
|-----------|------|
| `start_all.sh` | MCP サーバー + API + フロントエンドを起動 |
| `stop_all.sh` | 全サービスを停止 |
| `start_mcp_servers.sh` | MCP サーバーのみ起動（ポート 8000、8001）|
| `stop_mcp_servers.sh` | MCP サーバーを停止 |
| `start_api.sh` | FastAPI バックエンドを起動（ポート 8080）|
| `start_frontend.sh` | Next.js フロントエンドを起動（ポート 3000）|

### ML（`scripts/ml/`）

| スクリプト | 説明 |
|-----------|------|
| `run_ml_quant_metrics.py` | LightGBM モデルの学習と評価 |
| `batch_process.py` | 複数ティッカーの一括分析 |
| `process_layer1.py` | LLM によるニュース関連性フィルタリング |

### RAG（`scripts/rag/`）

| スクリプト | 説明 |
|-----------|------|
| `build_event_memory_batch.py` | ティッカー用 ChromaDB イベントメモリの構築 |
| `query_event_memory.py` | セマンティック検索でイベントメモリを照会 |
| `export_events.py` | イベントを JSON にエクスポート |
| `list_tickers.py` | イベントメモリ内のティッカー一覧表示 |

### データ（`scripts/data/`）

| スクリプト | 説明 |
|-----------|------|
| `download_stock_data.py` | 株式の過去 OHLC データをダウンロード |
| `download_crypto_data.py` | 暗号資産の過去 OHLC データをダウンロード |
| `daily_harvester.py` | 毎日のニュース自動収集 |

### ユーティリティ（`scripts/utils/`）

| スクリプト | 説明 |
|-----------|------|
| `manual_run.py` | インタラクティブ CLI |
| `test_dataflows.py` | データプロバイダー接続テスト |

## MCP サーバー

市場データとニュース検索は直接呼び出しではなく、MCP サーバー経由で提供されます。

**市場データサーバー**（`mcp_servers/market_data/`）— ポート 8000
- ツール: `get_us_stock_quote`、`get_stock_data`（SMA、MACD、ボリンジャーバンド付き）

**ニュース検索サーバー**（`mcp_servers/news_search/`）— ポート 8001
- ツール: `search_news_with_duckduckgo`、`search_news_with_tavily`

デフォルト以外のアドレスで動作する場合は `.env` で設定してください：

```bash
MCP_MARKET_DATA_URL=http://127.0.0.1:8000/mcp
MCP_NEWS_SEARCH_URL=http://127.0.0.1:8001/mcp
```

**トラブルシューティング：**

```bash
# ポートが使用中の場合
lsof -i :8000
kill <PID>

# 実行中のサーバーを確認
ps aux | grep mcp_servers
```

## プロジェクト構成

### コアエージェントシステム
- `app/graph_multi.py` — マルチエージェント LangGraph オーケストレーション（Fan-out/Fan-in）
- `app/state.py` — マルチエージェント通信用 AgentState
- `app/llm_config.py` — LLM プロバイダー設定（Claude / OpenAI）
- `app/embedding_config.py` — 埋め込みモデル設定

### ツールとデータソース
- `app/tools/finance_tools.py` — LangChain ツール（相場、履歴データ、ニュース、MCP 経由）
- `app/tools/enhanced_tools.py` — 拡張ツール
- `app/tools/quant_tool.py` — 定量分析ツール
- `app/mcp_client/finance_client.py` — MCP クライアント

### MCP サーバー
- `mcp_servers/market_data/` — 市場データサーバー（yfinance ラッパー）
- `mcp_servers/news_search/` — ニュース検索サーバー（DuckDuckGo + Tavily）

### FastAPI バックエンド
- `app/api/main.py` — アプリケーションエントリーポイント
- `app/api/routes/analyze.py` — 分析エンドポイント
- `app/api/routes/stocks.py` — 株式データエンドポイント
- `app/api/routes/crypto.py` — 暗号資産エンドポイント
- `app/api/routes/history.py` — エージェント実行履歴
- `app/api/routes/okx.py` — OKX 取引所連携
- `app/database/` — SQLite スキーマ、エージェント履歴、OHLC ストレージ

### 機械学習と定量分析
- `app/ml/model_trainer.py` — 時系列 CV 付き LightGBM 学習
- `app/ml/feature_engine.py` — 特徴量エンジニアリングパイプライン
- `app/ml/features.py` — テクニカル指標特徴量
- `app/ml/shap_explainer.py` — SHAP 説明可能性
- `app/ml/generate_report.py` — ML 予測レポート生成

### RAG とイベントメモリ
- `app/rag/build_event_memory.py` — ChromaDB イベントメモリの構築
- `app/rag/rag_tools.py` — RAG クエリツール

### レポート生成
- `app/reporting/run_context.py` — レポート実行コンテキスト
- `app/reporting/writer.py` — JSON/Markdown ライター
- `app/quant/generate_report.py` — 定量分析レポート
- `app/news/generate_report.py` — ニュースセンチメントレポート
- `app/social/generate_report.py` — ソーシャルセンチメントレポート

### フロントエンド（Next.js）
- `frontend/src/app/` — Next.js アプリディレクトリ
- `frontend/src/components/` — React コンポーネント
- `frontend/tsconfig.json` — TypeScript strict mode 有効
- `frontend/eslint.config.mjs` — ESLint 設定（TypeScript ルール、明示的な `any` 禁止）

## アーキテクチャ

```
ユーザークエリ
    ↓
┌─────────────────────────────────────┐
│   マルチエージェントオーケストレーター（CIO）│
└─────────────────────────────────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │ Quant  │  │  News  │  │ Social │
    │エージェント│  │エージェント│  │エージェント│
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌────────┐  ┌────────┐  ┌────────┐
    │  MCP   │  │  MCP   │  │ Reddit │
    │ 市場   │  │ ニュース│  │  API   │
    │ データ │  │ 検索   │  │        │
    └────────┘  └────────┘  └────────┘
         ↓           ↓           ↓
    ┌─────────────────────────────────┐
    │   ML モデル & RAG メモリ         │
    │  (LightGBM, ChromaDB, SHAP)     │
    └─────────────────────────────────┘
                    ↓
            最終投資判断
```

Quant・News・Social エージェントが並列実行され、それぞれ構造化レポートを生成します。CIO エージェントが3つのレポートを統合し、最終推奨を `data/reports/{run_id}_{asset}/` に保存します。

## コード品質

### バックエンド（Python）

[Ruff](https://docs.astral.sh/ruff/) でリントとフォーマットを管理（`pyproject.toml` で設定）: 行長 100、Python 3.13、ルール E/F/I/N/B。

```bash
uv run ruff format .          # フォーマット
uv run ruff check --fix .     # リント + 自動修正
uv run pytest tests/          # テスト
```

### フロントエンド（TypeScript）

- **TypeScript Strict Mode**: `tsconfig.json` で有効化、型安全性を確保
- **ESLint**: Next.js と TypeScript のルールを設定
  - `@typescript-eslint/no-explicit-any` を強制（エラーレベル）
  - `eslint-config-next` で Next.js ベストプラクティスに準拠

```bash
cd frontend
pnpm lint                     # ESLint 実行
pnpm lint:fix                 # ESLint 問題を自動修正
pnpm type-check               # TypeScript 型チェック
```

## コントリビューション

### バックエンド
1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `uv run pytest tests/`

### フロントエンド
1. `cd frontend && pnpm lint:fix`
2. `pnpm type-check`
3. TypeScript strict mode に準拠（`any` 型禁止）

すべてのチェックが通過したら Pull Request を送信してください。

## ライセンス

リポジトリのデフォルト設定に準じます。
