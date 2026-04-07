# Daily Email Digest Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scheduled daily email digest that sends configured multi-ticker technical snapshots, one macro news summary, and one concise CIO conclusion through SMTP.

**Architecture:** Keep the new digest flow isolated from the existing interactive single-asset graph. Add a small digest package for config, rendering, and orchestration; reuse existing quant and news entrypoints behind narrow adapters; register one APScheduler job that loads config, generates a persisted digest payload, renders text and HTML email bodies, and sends them through a dedicated email service.

**Tech Stack:** Python 3.13, FastAPI, APScheduler, standard-library email/SMTP, pytest, Ruff, existing LangChain tools and LLM integration

---

## File Map

- Create: `app/digest/__init__.py`
  - Package marker exporting the digest entrypoints used by scheduler/task code.
- Create: `app/digest/config.py`
  - Load env-driven digest settings, normalize tickers and recipients, validate time/timezone, and build the digest cron trigger.
- Create: `app/digest/models.py`
  - TypedDict contracts for `DailyDigestConfig`, `DailyDigestPayload`, `TechnicalSection`, `MacroNewsSection`, `CioSummarySection`, `EmailContent`, and delivery metadata.
- Create: `app/digest/render.py`
  - Render `digest.json` payload into deterministic `text/plain` and minimal `text/html` variants plus the email subject.
- Create: `app/digest/technical.py`
  - Build one technical section per ticker, routing equities to the existing quant report path and crypto to the Yahoo-compatible technical tool, with a bounded concurrency semaphore.
- Create: `app/digest/macro_news.py`
  - Query macro news once, filter/dedupe articles inside the digest window, apply the “missing timestamp is tolerated” rule, and summarize to 3-5 bullets.
- Create: `app/digest/cio.py`
  - Build the compact digest-level CIO summary with max-token and max-sentence enforcement.
- Create: `app/digest/generator.py`
  - Orchestrate the full digest run, preserve configured ticker order, persist `digest.json` / `email.txt` / `email.html`, and call the email service.
- Create: `app/services/email_service.py`
  - Build and send the multipart email through SMTP and return structured delivery status.
- Create: `app/tasks/send_daily_digest.py`
  - Scheduler entrypoint that loads config and runs the digest generator.
- Modify: `app/api/main.py`
  - Register the daily digest scheduler job when config is valid and enabled.
- Modify: `.env.example`
  - Document the new digest and SMTP environment variables.
- Create: `tests/digest/test_config.py`
  - Config defaults, invalid time/timezone handling, ticker normalization fallback, recipient filtering, sender fallback.
- Create: `tests/digest/test_render.py`
  - Subject/text/html rendering tests and output shape assertions.
- Create: `tests/digest/test_generator.py`
  - Orchestration, concurrency ordering, graceful degradation, persistence, and delivery metadata tests.
- Create: `tests/services/test_email_service.py`
  - SMTP success/error/skip paths and multipart message assertions.
- Modify: `tests/api/test_arq_scheduler.py`
  - Scheduler registration coverage for the new daily digest job.

## Chunk 1: Config And Schedule Validation

### Task 1: Lock the digest config contract with failing tests

**Files:**
- Create: `tests/digest/test_config.py`
- Test: `tests/digest/test_config.py`

- [ ] **Step 1: Write the failing config tests**

```python
from app.digest.config import DEFAULT_MACRO_QUERY, build_daily_digest_trigger, load_daily_digest_config


def test_load_daily_digest_config_defaults(monkeypatch):
    for key in (
        "DAILY_DIGEST_ENABLED",
        "DAILY_DIGEST_TIME",
        "DAILY_DIGEST_TIMEZONE",
        "DAILY_DIGEST_RECIPIENTS",
        "DAILY_DIGEST_FROM",
        "DAILY_DIGEST_TICKERS",
        "DAILY_DIGEST_MACRO_QUERY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_USE_STARTTLS",
        "SMTP_USE_SSL",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = load_daily_digest_config()
    assert cfg["enabled"] is False
    assert cfg["time"] == "08:00"
    assert cfg["timezone"] == "Asia/Shanghai"
    assert cfg["macro_query"] == DEFAULT_MACRO_QUERY
    assert cfg["tickers"] == ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BTC", "ETH"]


def test_build_daily_digest_trigger_rejects_invalid_time(monkeypatch):
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIME", "25:61")
    cfg = load_daily_digest_config()
    assert build_daily_digest_trigger(cfg) is None


def test_build_daily_digest_trigger_rejects_invalid_timezone(monkeypatch):
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIMEZONE", "Asia/Invalid")
    cfg = load_daily_digest_config()
    assert build_daily_digest_trigger(cfg) is None


def test_load_daily_digest_config_filters_bad_recipients(monkeypatch):
    monkeypatch.setenv("DAILY_DIGEST_RECIPIENTS", "ok@example.com,not-an-email")
    cfg = load_daily_digest_config()
    assert cfg["recipients"] == ["ok@example.com"]


def test_load_daily_digest_config_falls_back_to_default_tickers(monkeypatch):
    monkeypatch.setenv("DAILY_DIGEST_TICKERS", " , , ")
    cfg = load_daily_digest_config()
    assert cfg["tickers"] == ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BTC", "ETH"]


def test_load_daily_digest_config_uses_smtp_username_as_sender(monkeypatch):
    monkeypatch.delenv("DAILY_DIGEST_FROM", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "digest@example.com")
    cfg = load_daily_digest_config()
    assert cfg["sender"] == "digest@example.com"


def test_load_daily_digest_config_falls_back_when_smtp_port_is_invalid(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "not-a-number")
    cfg = load_daily_digest_config()
    assert cfg["smtp_port"] == 587


def test_load_daily_digest_config_logs_ticker_fallback_and_dropped_recipients(monkeypatch, caplog):
    monkeypatch.setenv("DAILY_DIGEST_TICKERS", " , , ")
    monkeypatch.setenv("DAILY_DIGEST_RECIPIENTS", "ok@example.com,not-an-email")
    cfg = load_daily_digest_config()
    assert cfg["tickers"][0] == "AAPL"
    assert cfg["recipients"] == ["ok@example.com"]
    assert "falling back to default tickers" in caplog.text
    assert "dropped " in caplog.text
    assert "invalid recipient" in caplog.text
```

- [ ] **Step 2: Run the new config tests and confirm they fail**

Run: `uv run pytest tests/digest/test_config.py -q`
Expected: FAIL because `app/digest/config.py` and the digest config helpers do not exist yet.

### Task 2: Implement digest config parsing and schedule validation

**Files:**
- Create: `app/digest/__init__.py`
- Create: `app/digest/config.py`
- Create: `app/digest/models.py`
- Modify: `.env.example`
- Test: `tests/digest/test_config.py`

- [ ] **Step 3: Write the minimal digest config implementation**

```python
DEFAULT_MACRO_QUERY = "US stock market macro economy Fed earnings bitcoin ethereum"
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BTC", "ETH"]


def load_daily_digest_config() -> DailyDigestConfig:
    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        logger.warning("Invalid SMTP_PORT=%r; falling back to 587", smtp_port_raw)
        smtp_port = 587
    tickers = _normalize_tickers(os.getenv("DAILY_DIGEST_TICKERS"))
    if not tickers:
        logger.warning("Daily digest ticker list is empty after normalization; falling back to default tickers")
        tickers = DEFAULT_TICKERS
    raw_recipients = os.getenv("DAILY_DIGEST_RECIPIENTS", "")
    recipients, dropped_recipient_count = _filter_recipients_with_count(raw_recipients)
    if dropped_recipient_count:
        logger.warning("Daily digest dropped %d invalid recipient(s)", dropped_recipient_count)
    return {
        "enabled": os.getenv("DAILY_DIGEST_ENABLED", "false").lower() == "true",
        "time": os.getenv("DAILY_DIGEST_TIME", "08:00"),
        "timezone": os.getenv("DAILY_DIGEST_TIMEZONE", "Asia/Shanghai"),
        "tickers": tickers,
        "macro_query": os.getenv("DAILY_DIGEST_MACRO_QUERY", DEFAULT_MACRO_QUERY),
        "recipients": recipients,
        "sender": _resolve_sender(),
        "smtp_host": os.getenv("SMTP_HOST"),
        "smtp_port": smtp_port,
        "smtp_username": os.getenv("SMTP_USERNAME"),
        "smtp_password": os.getenv("SMTP_PASSWORD"),
        "smtp_use_starttls": os.getenv("SMTP_USE_STARTTLS", "true").lower() == "true",
        "smtp_use_ssl": os.getenv("SMTP_USE_SSL", "false").lower() == "true",
    }


def build_daily_digest_trigger(config: DailyDigestConfig) -> CronTrigger | None:
    try:
        hour, minute = _parse_hh_mm(config["time"])
        tz = ZoneInfo(config["timezone"])
    except Exception:
        return None
    return CronTrigger(hour=hour, minute=minute, timezone=tz)
```

Transport-conflict enforcement note: Chunk 1 only parses SMTP booleans; the spec rule for `SMTP_USE_STARTTLS=true` plus `SMTP_USE_SSL=true` being invalid is enforced and tested in Chunk 2 inside `app/services/email_service.py`, where the send/skip decision actually happens.

Invalid time/timezone logging note: Chunk 1 keeps `build_daily_digest_trigger()` side-effect-free and returns `None` on invalid schedule config. The required configuration-error logging is owned by Chunk 3 in `configure_daily_digest_job()` when registration is attempted.

Ticker-fallback and dropped-recipient logging note: Chunk 1 owns these logs inside `load_daily_digest_config()` because normalization happens there, not in later chunks.

- [ ] **Step 4: Add the new digest-related env examples**

```env
DAILY_DIGEST_ENABLED=false
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

- [ ] **Step 5: Re-run the config tests**

Run: `uv run pytest tests/digest/test_config.py -q`
Expected: PASS

- [ ] **Step 6: Commit chunk 1**

```bash
git add .env.example app/digest/__init__.py app/digest/config.py app/digest/models.py tests/digest/test_config.py
git commit -m "feat(digest): add config and validation"
```

## Chunk 2: Email Rendering And SMTP Delivery

### Task 5: Lock subject/text/html rendering with failing tests

**Files:**
- Create: `tests/digest/test_render.py`
- Test: `tests/digest/test_render.py`

- [ ] **Step 12: Write rendering regression tests**

```python
def test_render_digest_email_returns_subject_text_and_html():
    payload = {
        "meta": {"timezone": "Asia/Shanghai", "scheduled_time": "08:00", "digest_date": "2026-04-07"},
        "tickers": ["AAPL", "BTC"],
        "technical_sections": [
            {"ticker": "AAPL", "asset_type": "equity", "status": "ok", "summary": "AAPL trend improving.", "trend": "bullish", "error": None},
            {"ticker": "BTC", "asset_type": "crypto", "status": "error", "summary": "Technical snapshot unavailable for this run.", "trend": "neutral", "error": "timeout"},
        ],
        "macro_news": {"status": "ok", "window_start": "2026-04-06T08:00:00+08:00", "window_end": "2026-04-07T08:00:00+08:00", "summary_points": ["Fed watch remains the top macro risk."], "error": None},
        "cio_summary": {"status": "ok", "text": "Risk appetite is mixed.", "error": None},
    }
    email = render_digest_email(payload)
    assert email["subject"] == "Daily Market Digest | 2026-04-07"
    assert "AAPL" in email["text_body"]
    assert "Fed watch remains the top macro risk." in email["text_body"]
    assert "<html" in email["html_body"].lower()
    assert "Fed watch remains the top macro risk." in email["html_body"]
```

- [ ] **Step 13: Run the render test and confirm it fails**

Run: `uv run pytest tests/digest/test_render.py -q`
Expected: FAIL because `app/digest/render.py` does not exist yet.

### Task 6: Implement deterministic text/HTML rendering

**Files:**
- Create: `app/digest/render.py`
- Modify: `tests/digest/test_render.py`
- Test: `tests/digest/test_render.py`

- [ ] **Step 14: Implement the renderer**

```python
def render_digest_email(payload: DailyDigestPayload) -> EmailContent:
    digest_date = str(payload["meta"]["digest_date"])
    subject = f"Daily Market Digest | {digest_date}"
    text_body = _render_text(payload)
    html_body = _render_html(payload)
    return {"subject": subject, "text_body": text_body, "html_body": html_body}
```

- [ ] **Step 15: Re-run the render tests**

Run: `uv run pytest tests/digest/test_render.py -q`
Expected: PASS

### Task 7: Lock SMTP delivery behavior with failing tests

**Files:**
- Create: `tests/services/test_email_service.py`
- Test: `tests/services/test_email_service.py`

- [ ] **Step 16: Write SMTP service tests before implementing the service**

```python
def test_send_digest_email_sends_multipart_message(monkeypatch):
    config = {
        "recipients": ["alice@example.com"],
        "sender": "digest@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "digest@example.com",
        "smtp_password": "secret",
        "smtp_use_starttls": True,
        "smtp_use_ssl": False,
    }
    smtp = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp
    smtp_cm.__exit__.return_value = False
    smtp_cls = MagicMock(return_value=smtp_cm)
    monkeypatch.setattr("app.services.email_service.smtplib.SMTP", smtp_cls)
    result = send_digest_email("Daily Market Digest | 2026-04-07", "plain", "<html><body>html</body></html>", config)
    assert result["status"] == "sent"
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("digest@example.com", "secret")
    smtp_cls.assert_called_once_with("smtp.example.com", 587)
    sent_message = smtp.send_message.call_args.args[0]
    assert sent_message.get_content_type() == "multipart/alternative"


def test_send_digest_email_skips_when_recipients_missing():
    config = {"recipients": [], "sender": "digest@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_username": None, "smtp_password": None, "smtp_use_starttls": True, "smtp_use_ssl": False}
    result = send_digest_email("Subject", "plain", "<html></html>", {**config, "recipients": []})
    assert result["status"] == "skipped"


def test_send_digest_email_skips_conflicting_tls_modes():
    config = {"recipients": ["alice@example.com"], "sender": "digest@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_username": None, "smtp_password": None, "smtp_use_starttls": True, "smtp_use_ssl": False}
    result = send_digest_email("Subject", "plain", "<html></html>", {**config, "smtp_use_starttls": True, "smtp_use_ssl": True})
    assert result["status"] == "skipped"


def test_send_digest_email_skips_when_smtp_host_missing():
    config = {"recipients": ["alice@example.com"], "sender": "digest@example.com", "smtp_host": None, "smtp_port": 587, "smtp_username": None, "smtp_password": None, "smtp_use_starttls": True, "smtp_use_ssl": False}
    result = send_digest_email("Subject", "plain", "<html></html>", config)
    assert result["status"] == "skipped"


def test_send_digest_email_returns_error_when_send_fails(monkeypatch):
    config = {"recipients": ["alice@example.com"], "sender": "digest@example.com", "smtp_host": "smtp.example.com", "smtp_port": 465, "smtp_username": None, "smtp_password": None, "smtp_use_starttls": False, "smtp_use_ssl": True}
    smtp = MagicMock()
    smtp.send_message.side_effect = RuntimeError("boom")
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp
    smtp_cm.__exit__.return_value = False
    smtp_ssl_cls = MagicMock(return_value=smtp_cm)
    monkeypatch.setattr("app.services.email_service.smtplib.SMTP_SSL", smtp_ssl_cls)
    result = send_digest_email("Subject", "plain", "<html></html>", config)
    assert result["status"] == "error"
    assert "boom" in result["error"]
    smtp_ssl_cls.assert_called_once_with("smtp.example.com", 465)
```

- [ ] **Step 17: Run the service tests and confirm they fail**

Run: `uv run pytest tests/services/test_email_service.py -q`
Expected: FAIL because `app/services/email_service.py` does not exist yet.

### Task 8: Implement SMTP delivery with structured status

**Files:**
- Create: `app/services/email_service.py`
- Modify: `tests/services/test_email_service.py`
- Test: `tests/services/test_email_service.py`

- [ ] **Step 18: Implement the email service**

```python
def send_digest_email(subject: str, text_body: str, html_body: str, config: DailyDigestConfig) -> EmailDelivery:
    if not config["recipients"] or not config["sender"]:
        logger.warning("Skipping daily digest email because recipients or sender are missing")
        return {"status": "skipped", "subject": subject, "recipients": config["recipients"], "error": "missing recipients or sender"}
    if not config["smtp_host"]:
        logger.warning("Skipping daily digest email because SMTP host is missing")
        return {"status": "skipped", "subject": subject, "recipients": config["recipients"], "error": "missing smtp host"}
    if config["smtp_use_starttls"] and config["smtp_use_ssl"]:
        logger.warning("Skipping daily digest email because SMTP TLS settings conflict")
        return {"status": "skipped", "subject": subject, "recipients": config["recipients"], "error": "conflicting smtp tls settings"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config["sender"]
    msg["To"] = ", ".join(config["recipients"])
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    try:
        client_cls = smtplib.SMTP_SSL if config["smtp_use_ssl"] else smtplib.SMTP
        with client_cls(config["smtp_host"], config["smtp_port"]) as client:
            if config["smtp_use_starttls"]:
                client.starttls()
            if config["smtp_username"] and config["smtp_password"]:
                client.login(config["smtp_username"], config["smtp_password"])
            client.send_message(msg)
        logger.info("Sent daily digest email to %d recipient(s)", len(config["recipients"]))
        return {"status": "sent", "subject": subject, "recipients": config["recipients"], "error": None}
    except Exception as exc:
        logger.exception("Failed to send daily digest email")
        return {"status": "error", "subject": subject, "recipients": config["recipients"], "error": f"{type(exc).__name__}: {exc}"}
```

- [ ] **Step 19: Re-run the email service tests**

Run: `uv run pytest tests/services/test_email_service.py -q`
Expected: PASS

- [ ] **Step 20: Run the render and email-service slice together**

Run: `uv run pytest tests/digest/test_render.py tests/services/test_email_service.py -q`
Expected: PASS

- [ ] **Step 21: Commit chunk 2**

```bash
git add app/digest/render.py app/services/email_service.py tests/digest/test_render.py tests/services/test_email_service.py
git commit -m "feat(email): add digest rendering and delivery"
```

## Chunk 3: Digest Generation, Persistence, And Task Integration

### Task 9: Lock orchestration, ordering, and graceful degradation with failing tests

**Files:**
- Create: `tests/digest/test_generator.py`
- Test: `tests/digest/test_generator.py`

- [ ] **Step 22: Write generator tests before implementing orchestration**

```python
import asyncio
from datetime import datetime

import pytest
from app.digest.generator import generate_daily_digest
from app.digest.macro_news import build_macro_news_section


@pytest.fixture
def config():
    return {
        "enabled": True,
        "time": "08:00",
        "timezone": "Asia/Shanghai",
        "tickers": ["AAPL", "MSFT", "BTC"],
        "macro_query": "US stock market macro economy Fed earnings bitcoin ethereum",
        "recipients": ["alice@example.com"],
        "sender": "digest@example.com",
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "smtp_use_starttls": True,
        "smtp_use_ssl": False,
    }


async def fake_out_of_order_section_builder(ticker, run_dir):
    delays = {"AAPL": 0.03, "MSFT": 0.01, "BTC": 0.02}
    await asyncio.sleep(delays[ticker])
    return {
        "ticker": ticker,
        "asset_type": "crypto" if ticker == "BTC" else "equity",
        "status": "ok",
        "summary": f"{ticker} summary",
        "trend": "bullish",
        "error": None,
    }


@pytest.mark.asyncio
async def test_generate_daily_digest_preserves_configured_ticker_order(monkeypatch, tmp_path, config):
    monkeypatch.setattr("app.digest.generator.MAX_CONCURRENT_TECHNICAL_SECTIONS", 3)
    monkeypatch.setattr("app.digest.generator.build_technical_section", fake_out_of_order_section_builder)
    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)
    assert [section["ticker"] for section in payload["technical_sections"]] == ["AAPL", "MSFT", "BTC"]
    assert payload["run_id"].endswith("_daily_digest")


@pytest.mark.asyncio
async def test_generate_daily_digest_persists_json_text_and_html(monkeypatch, tmp_path, config):
    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)
    assert (base_dir / payload["run_id"] / "digest.json").exists()
    assert (base_dir / payload["run_id"] / "email.txt").exists()
    assert (base_dir / payload["run_id"] / "email.html").exists()


@pytest.mark.asyncio
async def test_generate_daily_digest_uses_default_digests_directory(monkeypatch, tmp_path, config):
    monkeypatch.chdir(tmp_path)
    payload = await generate_daily_digest(config)
    assert (tmp_path / "data" / "reports" / "digests" / payload["run_id"] / "digest.json").exists()


@pytest.mark.asyncio
async def test_generate_daily_digest_keeps_running_when_one_ticker_fails(monkeypatch, tmp_path, config):
    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)
    failing = next(section for section in payload["technical_sections"] if section["ticker"] == "BTC")
    assert failing["status"] == "error"
    assert failing["summary"] == "Technical snapshot unavailable for this run."
    assert failing["error"] is not None
    successful = next(section for section in payload["technical_sections"] if section["ticker"] == "AAPL")
    assert successful["error"] is None


def test_build_macro_news_section_keeps_missing_timestamp_articles_when_needed(config):
    section = build_macro_news_section(config)
    assert 3 <= len(section["summary_points"]) <= 5
    assert len(section["sources"]) <= 8
    assert datetime.fromisoformat(section["window_start"]).tzinfo is not None
    assert datetime.fromisoformat(section["window_end"]).tzinfo is not None


@pytest.mark.asyncio
async def test_generate_daily_digest_payload_matches_required_top_level_contract(monkeypatch, tmp_path, config):
    base_dir = tmp_path / "data" / "reports" / "digests"
    payload = await generate_daily_digest(config, base_dir=base_dir)
    assert set(payload) >= {"module", "run_id", "meta", "tickers", "technical_sections", "macro_news", "cio_summary", "email"}
    assert payload["module"] == "daily_digest"
    assert set(payload["meta"]) >= {"generated_at_utc", "timezone", "scheduled_time"}
    assert set(payload["email"]) >= {"status", "subject", "recipients"}
    assert isinstance(payload["macro_news"]["summary_points"], list)
    assert datetime.fromisoformat(payload["macro_news"]["window_start"]).tzinfo is not None
    assert datetime.fromisoformat(payload["macro_news"]["window_end"]).tzinfo is not None
    if payload["macro_news"]["status"] == "ok":
        assert payload["macro_news"]["error"] is None
    else:
        assert payload["macro_news"]["summary_points"] == []
```

- [ ] **Step 23: Run the generator tests and confirm they fail**

Run: `uv run pytest tests/digest/test_generator.py -q`
Expected: FAIL because the digest generator and helper modules do not exist yet.

### Task 10: Implement technical, macro-news, and CIO adapters

**Files:**
- Create: `app/digest/technical.py`
- Create: `app/digest/macro_news.py`
- Create: `app/digest/cio.py`
- Modify: `tests/digest/test_generator.py`
- Test: `tests/digest/test_generator.py`

- [ ] **Step 24: Implement the technical-section adapter with bounded concurrency support**

```python
MAX_CONCURRENT_TECHNICAL_SECTIONS = 3


async def build_technical_section(ticker: str, run_dir: Path) -> TechnicalSection:
    asset_type = "crypto" if classify_asset_type(ticker) == "crypto" else "equity"
    try:
        if asset_type == "equity":
            report = await asyncio.to_thread(generate_quant_report, ticker, str(run_dir / ticker))
            return _section_from_quant_report(report)
        stock_data = await asyncio.to_thread(get_stock_data.invoke, {"ticker": f"{ticker}-USD", "period": "3mo"})
        return _section_from_crypto_data(ticker, stock_data)
    except Exception as exc:
        return _technical_error_section(ticker, asset_type, exc)
```

- [ ] **Step 25: Implement macro-news filtering and tolerant timestamp handling**

```python
def build_macro_news_section(config: DailyDigestConfig, now: datetime | None = None) -> MacroNewsSection:
    raw = search_realtime_news.invoke({"query": config["macro_query"], "limit": 8})
    articles = _normalize_articles(raw)
    window_start, window_end = _digest_window(now, config["timezone"])
    filtered = _filter_articles_in_window(articles, window_start, window_end)
    tolerant = _backfill_missing_timestamp_articles(filtered, articles, minimum_count=3)
    deduped = _dedupe_articles(tolerant)
    summary_points = _summarize_to_bullets(deduped, minimum_points=3, maximum_points=5)
    return {
        "status": "ok",
        "query": config["macro_query"],
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "summary_points": summary_points,
        "sources": deduped[:8],
        "error": None,
    }
```

- [ ] **Step 26: Implement CIO synthesis with hard output trimming**

```python
def build_cio_summary(technical_sections: list[TechnicalSection], macro_news: MacroNewsSection) -> CioSummarySection:
    prompt = _compact_cio_prompt(technical_sections, macro_news)
    response = llm.invoke(
        [
            SystemMessage(content=DIGEST_CIO_SYSTEM),
            HumanMessage(content=prompt),
        ],
        max_tokens=300,
    )
    text = _keep_first_four_sentences(str(response.content))
    return {"status": "ok", "text": text, "error": None}
```

- [ ] **Step 27: Re-run the generator tests**

Run: `uv run pytest tests/digest/test_generator.py -q`
Expected: Still FAIL because the top-level orchestrator and scheduled task entrypoint are not implemented yet.

### Task 11: Implement digest orchestration, persistence, and scheduler task entrypoint

**Files:**
- Create: `app/digest/generator.py`
- Create: `app/tasks/send_daily_digest.py`
- Modify: `app/digest/__init__.py`
- Modify: `app/api/main.py`
- Modify: `tests/digest/test_generator.py`
- Modify: `tests/api/test_arq_scheduler.py`
- Test: `tests/digest/test_generator.py`
- Test: `tests/api/test_arq_scheduler.py`

- [ ] **Step 28: Add scheduler registration tests before changing `app/api/main.py`**

```python
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from unittest.mock import Mock

from app.api.main import configure_daily_digest_job


def test_configure_daily_digest_job_registers_cron_job(monkeypatch):
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIME", "08:00")
    monkeypatch.setenv("DAILY_DIGEST_TIMEZONE", "Asia/Shanghai")
    app = FastAPI()
    scheduler = Mock()

    configure_daily_digest_job(app, scheduler)

    digest_call = next(call for call in scheduler.add_job.call_args_list if call.kwargs["id"] == "daily_email_digest")
    assert digest_call.args[0].__name__ == "send_daily_digest"
    assert isinstance(digest_call.kwargs["trigger"], CronTrigger)
    assert str(digest_call.kwargs["trigger"].timezone) == "Asia/Shanghai"
    assert digest_call.kwargs["replace_existing"] is True
    assert digest_call.kwargs["max_instances"] == 1


def test_configure_daily_digest_job_skips_invalid_schedule(monkeypatch, caplog):
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_TIME", "99:99")
    app = FastAPI()
    scheduler = Mock()

    configure_daily_digest_job(app, scheduler)

    assert all(call.kwargs.get("id") != "daily_email_digest" for call in scheduler.add_job.call_args_list)
    assert "Skipping daily digest registration because digest schedule config is invalid" in caplog.text
```

- [ ] **Step 29: Run the scheduler tests to confirm the new assertions fail**

Run: `uv run pytest tests/api/test_arq_scheduler.py -q`
Expected: FAIL because `configure_daily_digest_job()` is not implemented yet.

- [ ] **Step 30: Implement the digest generator**

```python
async def generate_daily_digest(config: DailyDigestConfig, base_dir: Path | None = None) -> dict[str, object]:
    run_dir = _make_digest_run_dir(config, base_dir=base_dir)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TECHNICAL_SECTIONS)

    async def _bounded(ticker: str) -> TechnicalSection:
        async with semaphore:
            return await build_technical_section(ticker, run_dir)

    technical_sections = list(await asyncio.gather(*[_bounded(ticker) for ticker in config["tickers"]]))
    macro_news = await asyncio.to_thread(build_macro_news_section, config)
    cio_summary = await asyncio.to_thread(build_cio_summary, technical_sections, macro_news)
    payload = {
        "module": "daily_digest",
        "run_id": run_dir.name,
        "meta": _build_digest_meta(config),
        "tickers": config["tickers"],
        "technical_sections": technical_sections,
        "macro_news": macro_news,
        "cio_summary": cio_summary,
        "email": {"status": "skipped", "subject": "", "recipients": config["recipients"], "error": None},
    }
    email = render_digest_email(payload)
    _persist_digest_artifacts(run_dir, email["text_body"], email["html_body"])
    payload["email"] = send_digest_email(email["subject"], email["text_body"], email["html_body"], config)
    write_json(run_dir / "digest.json", payload)
    return payload
```

- [ ] **Step 31: Implement the scheduled task entrypoint and scheduler hook**

```python
async def send_daily_digest() -> dict[str, object]:
    config = load_daily_digest_config()
    if not config["enabled"]:
        return {"status": "skipped", "reason": "disabled"}
    return await generate_daily_digest(config)


def configure_daily_digest_job(app: FastAPI, scheduler: AsyncIOScheduler) -> None:
    cfg = load_daily_digest_config()
    if not cfg["enabled"]:
        return
    trigger = build_daily_digest_trigger(cfg)
    if trigger is None:
        logger.error("Skipping daily digest registration because digest schedule config is invalid")
        return
    scheduler.add_job(send_daily_digest, trigger=trigger, id="daily_email_digest", replace_existing=True, max_instances=1)
```

- [ ] **Step 32: Re-run the generator and scheduler tests**

Run: `uv run pytest tests/digest/test_generator.py tests/api/test_arq_scheduler.py -q`
Expected: PASS

### Task 12: Verify the full daily-digest slice

**Files:**
- Modify: `app/api/main.py`
- Modify: `.env.example`
- Create: `app/digest/__init__.py`
- Create: `app/digest/config.py`
- Create: `app/digest/models.py`
- Create: `app/digest/render.py`
- Create: `app/digest/technical.py`
- Create: `app/digest/macro_news.py`
- Create: `app/digest/cio.py`
- Create: `app/digest/generator.py`
- Create: `app/services/email_service.py`
- Create: `app/tasks/send_daily_digest.py`
- Create: `tests/digest/test_config.py`
- Create: `tests/digest/test_render.py`
- Create: `tests/digest/test_generator.py`
- Create: `tests/services/test_email_service.py`
- Modify: `tests/api/test_arq_scheduler.py`

- [ ] **Step 33: Run the digest-focused test suite**

Run: `uv run pytest tests/digest/test_config.py tests/digest/test_render.py tests/digest/test_generator.py tests/services/test_email_service.py tests/api/test_arq_scheduler.py -q`
Expected: PASS

- [ ] **Step 34: Run Ruff on the touched Python files**

Run: `uv run ruff check app/api/main.py app/digest app/services/email_service.py app/tasks/send_daily_digest.py tests/digest tests/services/test_email_service.py tests/api/test_arq_scheduler.py`
Expected: PASS

- [ ] **Step 35: Run formatting checks on the touched Python files**

Run: `uv run ruff format --check app/api/main.py app/digest app/services/email_service.py app/tasks/send_daily_digest.py tests/digest tests/services/test_email_service.py tests/api/test_arq_scheduler.py`
Expected: PASS

- [ ] **Step 36: Commit chunk 3**

```bash
git add .env.example app/api/main.py app/digest app/services/email_service.py app/tasks/send_daily_digest.py tests/digest tests/services/test_email_service.py tests/api/test_arq_scheduler.py
git commit -m "feat(digest): add daily email digest pipeline"
```
