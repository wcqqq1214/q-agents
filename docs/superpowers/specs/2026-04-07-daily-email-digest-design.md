# Daily Email Digest Design

## Goal

Add a scheduled email digest that sends one concise daily market report to a fixed recipient list. The digest must include:

- a technical snapshot for each configured ticker
- one global macro and market news summary for the day
- one concise CIO-style conclusion for the whole digest

The first release targets fixed configuration from environment variables, with defaults for the ticker universe and send schedule.

## Scope

- Add a new digest pipeline separate from the existing single-asset `run_once()` flow.
- Reuse existing quant and news capabilities where practical, but optimize for one multi-ticker email rather than nine independent full reports.
- Schedule the digest with APScheduler using configurable time and timezone.
- Send email through SMTP with recipients configured in `.env`.
- Persist the digest payload and rendered email snapshot for inspection.

## Out Of Scope

- Per-user subscriptions, per-user watchlists, or per-user send schedules
- A frontend settings UI for digest management
- Database-backed recipient management
- Automatic email retry queues or delivery tracking
- Reusing the social report in the daily digest

## User-Facing Behavior

When the daily digest job runs, the system should:

1. load the configured ticker universe
2. generate a concise technical section for each ticker
3. generate one global macro news section
4. generate one digest-level CIO summary
5. render a compact plain-text email body
6. persist digest artifacts under `data/reports/digests/...`
7. send the email to all configured recipients when SMTP and recipients are available

If email sending is not possible because recipients or SMTP settings are missing, the system should still build and persist the digest and emit a warning log instead of failing the whole job.

## Default Configuration

The first release should be driven entirely by environment variables:

```env
DAILY_DIGEST_ENABLED=true
DAILY_DIGEST_TIME=08:00
DAILY_DIGEST_TIMEZONE=Asia/Shanghai
DAILY_DIGEST_RECIPIENTS=alice@example.com,bob@example.com
DAILY_DIGEST_FROM=bot@example.com
DAILY_DIGEST_TICKERS=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,BTC,ETH
DAILY_DIGEST_MACRO_QUERY=US stock market macro economy Fed earnings bitcoin ethereum

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=bot@example.com
SMTP_PASSWORD=secret
SMTP_USE_STARTTLS=true
SMTP_USE_SSL=false
```

Defaults:

- `DAILY_DIGEST_ENABLED`: `false` when unset
- `DAILY_DIGEST_TIME`: `08:00`
- `DAILY_DIGEST_TIMEZONE`: `Asia/Shanghai`
- `DAILY_DIGEST_TICKERS`: `AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,BTC,ETH`
- `DAILY_DIGEST_MACRO_QUERY`: a built-in market-wide query string if unset

Validation rules:

- invalid `DAILY_DIGEST_TIME` or `DAILY_DIGEST_TIMEZONE`
  - do not crash API startup
  - log a configuration error
  - skip daily digest job registration
- empty or invalid ticker list after normalization
  - log a warning
  - fall back to the built-in default list
- malformed recipients
  - drop invalid addresses
  - log how many addresses were dropped
  - continue digest generation
  - skip email sending if no valid recipients remain
- `SMTP_USE_STARTTLS=true` and `SMTP_USE_SSL=true`
  - treat as invalid transport configuration
  - generate the digest but mark email delivery as skipped with an error reason

## Digest Date Semantics

The digest date is defined in `DAILY_DIGEST_TIMEZONE` at the moment the job runs.

This digest date must be used consistently for:

- email subject line
- `run_id`
- persisted artifact directory
- macro news time-window filtering

For the first release, the macro news window means the 24 hours immediately preceding digest generation time in `DAILY_DIGEST_TIMEZONE`.

## Architecture

### 1. Digest Configuration Layer

Add a small configuration helper that reads and validates daily digest settings from environment variables. This layer should normalize:

- enable flag
- schedule time and timezone
- recipient list
- sender address
- ticker list
- macro query
- SMTP settings

This keeps scheduler registration, digest generation, and email transport independent from raw `os.getenv()` parsing.

### 2. Digest Pipeline

Add a dedicated digest pipeline under a new `app/digest/` package. This package should orchestrate the full daily report without changing the existing interactive graph flow.

Suggested responsibilities:

- `app/digest/config.py`
  - parse and validate digest configuration
- `app/digest/generator.py`
  - orchestrate the whole digest run
- `app/digest/render.py`
  - convert the structured digest payload into email-ready plain text

The pipeline should return a structured digest object that includes:

- run metadata
- configured ticker list
- one technical block per ticker
- one macro news block
- one CIO summary block
- file paths for persisted artifacts

### 3. Technical Snapshot Generation

The digest should use a dedicated technical snapshot adapter interface and route by asset type.

Asset routing rules:

- equities such as `AAPL`, `NVDA`
  - reuse the existing quant report generation path and adapt its structured output into a digest section
- crypto assets such as `BTC`, `ETH`
  - use the Yahoo-compatible technical data path with symbol mapping `BTC -> BTC-USD`, `ETH -> ETH-USD`
  - compute the same indicator family used in the digest section
  - do not require ML enrichment in the first release

This avoids relying on `get_local_stock_data`, which is limited to Magnificent Seven equities, while keeping the digest output shape consistent across stocks and crypto.

For each ticker, the digest should extract:

- ticker
- asset_type
- status
- trend
- summary
- support
- resistance
- last close
- SMA 20
- MACD line
- MACD signal
- optional ML signal fields when present

The digest should not embed the full markdown quant report verbatim. Instead, it should render a compact line-oriented summary per ticker.

### 4. Macro News Generation

The digest should generate one global macro and market news section per run instead of calling the current per-asset news generator for every ticker.

This requires a lightweight macro news step that:

- searches once using the configured macro query
- filters to articles published within the prior 24-hour digest window
- deduplicates by canonical URL when available, otherwise by normalized title
- keeps between 3 and 8 unique source articles when available
- summarizes them into 3-5 concise bullet points
- preserves source metadata in the persisted digest payload

The digest email should show only the concise bullet points. The underlying JSON payload can keep article metadata for debugging and later extension.

### 5. Digest-Level CIO Summary

Add a digest-specific CIO summarization step that consumes:

- all ticker technical snapshots
- the macro news summary

The output should be a short conclusion focused on:

- overall market tone
- strongest or weakest setups in the configured universe
- top macro risks to watch

This is intentionally different from the current per-asset CIO flow.

### 6. Email Transport

Add a dedicated email service, for example `app/services/email_service.py`, that is responsible for:

- building a plain-text email message
- parsing recipients
- connecting to SMTP
- STARTTLS or SSL handling
- sending the message
- logging success and failure

The digest pipeline should not contain transport-specific logic beyond calling this service.

### 7. Scheduler Integration

Register the daily digest job from `app/api/main.py` alongside the existing APScheduler jobs.

Expected behavior:

- only register the job when `DAILY_DIGEST_ENABLED` is true
- parse `DAILY_DIGEST_TIME` and `DAILY_DIGEST_TIMEZONE`
- create one cron job with `replace_existing=True` and `max_instances=1`
- point the job at a dedicated task entrypoint, such as `app/tasks/send_daily_digest.py`

Deployment boundary for the first release:

- the digest scheduler is single-leader only
- only one running application process or replica may enable `DAILY_DIGEST_ENABLED=true`
- preventing duplicate sends across multiple replicas is an operational requirement for v1, not a distributed-lock feature implemented in this change

## Interfaces

The implementation plan should use explicit typed interfaces close to the following shape.

```python
class DailyDigestConfig(TypedDict):
    enabled: bool
    time: str
    timezone: str
    tickers: list[str]
    macro_query: str
    recipients: list[str]
    sender: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_starttls: bool
    smtp_use_ssl: bool


class TechnicalSection(TypedDict, total=False):
    ticker: str
    asset_type: str
    status: str  # ok | error
    summary: str
    trend: str
    levels: dict[str, float | None]
    indicators: dict[str, float | None]
    ml_signal: dict[str, object] | None
    error: str | None


class MacroNewsSection(TypedDict, total=False):
    status: str  # ok | error
    query: str
    window_start: str
    window_end: str
    summary_points: list[str]
    sources: list[dict[str, object]]
    error: str | None


class CioSummarySection(TypedDict, total=False):
    status: str  # ok | error
    text: str
    error: str | None


class EmailDelivery(TypedDict, total=False):
    status: str  # sent | skipped | error
    subject: str
    recipients: list[str]
    error: str | None


def load_daily_digest_config() -> DailyDigestConfig: ...
def build_technical_section(ticker: str) -> TechnicalSection: ...
def build_macro_news_section(config: DailyDigestConfig) -> MacroNewsSection: ...
def build_cio_summary(
    technical_sections: list[TechnicalSection],
    macro_news: MacroNewsSection,
) -> CioSummarySection: ...
def send_digest_email(
    subject: str,
    body: str,
    config: DailyDigestConfig,
) -> EmailDelivery: ...
```

These names may be adapted to repository conventions during implementation, but the interface boundaries and required fields should stay stable.

## Data Contract

The digest pipeline must produce a structured JSON payload with these required top-level keys:

- `module`
- `run_id`
- `meta`
- `tickers`
- `technical_sections`
- `macro_news`
- `cio_summary`
- `email`

Required subfields:

- `meta.generated_at_utc`
- `meta.timezone`
- `meta.scheduled_time`
- `technical_sections[*].ticker`
- `technical_sections[*].asset_type`
- `technical_sections[*].status`
- `technical_sections[*].summary`
- `macro_news.status`
- `macro_news.summary_points`
- `cio_summary.status`
- `cio_summary.text`
- `email.status`
- `email.subject`
- `email.recipients`

Example:

```json
{
  "module": "daily_digest",
  "run_id": "20260407_080000_daily_digest",
  "meta": {
    "generated_at_utc": "2026-04-07T00:00:00+00:00",
    "timezone": "Asia/Shanghai",
    "scheduled_time": "08:00"
  },
  "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BTC", "ETH"],
  "technical_sections": [
    {
      "ticker": "AAPL",
      "asset_type": "stocks",
      "status": "ok",
      "trend": "bullish",
      "summary": "Short technical sentence.",
      "levels": {"support": 198.0, "resistance": 205.0},
      "indicators": {
        "last_close": 201.0,
        "sma_20": 196.0,
        "macd_line": 1.2,
        "macd_signal": 0.9
      }
    }
  ],
  "macro_news": {
    "status": "ok",
    "summary_points": ["Point 1", "Point 2", "Point 3"],
    "sources": []
  },
  "cio_summary": {
    "status": "ok",
    "text": "Concise digest-level CIO conclusion."
  },
  "email": {
    "subject": "Daily Market Digest | 2026-04-07",
    "recipients": ["alice@example.com"],
    "status": "sent"
  }
}
```

## Artifact Persistence

Persist each digest run under a dedicated directory, for example:

- `data/reports/digests/<run_id>/digest.json`
- `data/reports/digests/<run_id>/email.txt`

`digest.json` is the source of truth for the run. `email.txt` is the rendered plain-text snapshot that was intended for delivery.

Retention for the first release follows the current reports behavior: keep artifacts until manually cleaned up. No automatic retention or pruning policy is added in this change.

## Email Rendering

The first release should send a compact plain-text email. The body should contain:

- header with date and ticker coverage
- one short technical subsection per ticker
- one macro news subsection with 3-5 bullets
- one CIO summary subsection with 2-4 sentences

The renderer should avoid dumping full markdown reports into email. The digest must be readable in a normal email client without scrolling through long report blocks.

Formatting rules:

- preserve the configured ticker order
- render each ticker in no more than two compact lines
- inline unavailable sections at the ticker or section where they occur
- do not add a separate error appendix in v1

## Failure Handling

The digest pipeline must degrade gracefully.

### Per-Ticker Failure

If one ticker fails during technical snapshot generation:

- keep the digest running
- include a `status=error` record for that ticker
- render a short unavailable line in the email for that ticker
- log the underlying exception

### Macro News Failure

If macro news generation fails:

- keep the digest running
- record `macro_news.status=error`
- render a short fallback line such as `Macro news unavailable for this run.`

### CIO Summary Failure

If digest-level CIO synthesis fails:

- keep the digest running
- record `cio_summary.status=error`
- render a deterministic fallback sentence based on available technical and macro sections

### Email Failure

If SMTP delivery fails:

- do not discard the generated digest
- persist `digest.json` and `email.txt`
- record send failure metadata in the digest payload
- log the error

Automatic retry logic is not required in the first release.

## Logging

Add structured logging around:

- digest job start and end
- number of configured tickers
- per-ticker failures
- macro news failure
- CIO summary failure
- email sent or skipped
- SMTP delivery failure

This work should use logging, not `print`.

Logging must not include:

- SMTP passwords or auth secrets
- full recipient lists

Log recipient counts instead of raw recipient addresses.

## Integration Points

- `app/api/main.py`
  - register the scheduled daily digest job
- existing quant report module
  - reused as the technical analysis source
- existing local or news tool stack
  - reused for global macro news search
- new email service
  - isolated SMTP transport

The new digest pipeline should not change the behavior of the current `/api/analyze` interactive flow.

## Testing

Add tests that cover the new flow without relying on real SMTP or live external APIs.

### Configuration Tests

- defaults for time, timezone, and ticker list
- recipient parsing from comma-separated env values
- disabled behavior when the feature flag is false

### Digest Aggregation Tests

- successful aggregation with mocked technical snapshots, news, and CIO summary
- continued execution when one ticker fails
- fallback behavior when macro news or CIO synthesis fails

### Email Rendering Tests

- rendered plain-text email contains all configured tickers
- rendered body includes macro news and CIO sections
- unavailable ticker rows render compactly and clearly

### Scheduler Tests

- scheduler registers the digest job only when enabled
- trigger uses configured time and timezone
- job is registered with `replace_existing=True`

### Email Service Tests

- SMTP success path
- SMTP authentication or connection failure path
- behavior when recipients are missing

## Implementation Notes

- The first release should prefer small, deterministic adapters around existing quant and news code rather than refactoring the current graph.
- Social sentiment is intentionally excluded from the digest because it is not part of the requested email contract and would add cost and noise.
- If the existing quant generator proves too heavy for nine tickers in one run, the plan may split out a lighter technical snapshot helper, but that optimization does not need to be designed as a separate subsystem yet.
