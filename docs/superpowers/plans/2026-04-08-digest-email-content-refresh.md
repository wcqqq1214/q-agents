# Digest Email Content Refresh Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the daily digest email so the technical section becomes a compact price board, macro news becomes the most detailed section, and the CIO section remains unchanged.

**Architecture:** Keep the change narrowly scoped to the digest payload contract, technical-section adapter, and email renderer. Add one new `daily_change_pct` field to the technical payload, redesign text/HTML rendering around that field and the existing macro news sources, and leave scheduler, delivery, and CIO generation untouched.

**Tech Stack:** Python 3.13, pytest, Ruff, existing digest pipeline, standard-library HTML/text rendering

---

## File Map

- Modify: `app/digest/models.py`
  - Add `daily_change_pct` to `TechnicalSection`.
- Modify: `app/digest/technical.py`
  - Compute `daily_change_pct` for equities and crypto.
  - Keep existing fields for JSON payload compatibility.
- Modify: `app/digest/render.py`
  - Render technical overview as compact price/change lines.
  - Render macro news as 3 detailed items with deterministic 2-sentence summaries and links.
  - Keep CIO rendering logic unchanged.
- Modify: `tests/digest/test_render.py`
  - Lock the new text and HTML output shape.
- Modify: `tests/digest/test_generator.py`
  - Lock `daily_change_pct` in generated sections and verify rendering fallbacks are supported by payloads.

## Chunk 1: Lock The New Rendering Contract

### Task 1: Replace the old render expectations with failing tests

**Files:**
- Modify: `tests/digest/test_render.py`
- Test: `tests/digest/test_render.py`

- [ ] **Step 1: Rewrite the render tests to assert the new technical overview**

```python
def test_render_digest_email_returns_price_board_and_detailed_macro_news():
    payload = {
        "meta": {
            "timezone": "Asia/Shanghai",
            "scheduled_time": "08:00",
            "digest_date": "2026-04-08",
        },
        "technical_sections": [
            {
                "ticker": "AAPL",
                "asset_type": "equity",
                "status": "ok",
                "summary": "unused",
                "trend": "bullish",
                "daily_change_pct": 1.234,
                "indicators": {"last_close": 254.48},
                "error": None,
            },
            {
                "ticker": "BTC",
                "asset_type": "crypto",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": None,
                "indicators": {"last_close": 68078.72},
                "error": None,
            },
        ],
        "macro_news": {
            "status": "ok",
            "summary_points": [],
            "sources": [
                {
                    "title": "Fed repricing hits risk assets",
                    "source": "Reuters",
                    "url": "https://example.com/fed",
                    "snippet": "Treasury yields climbed after stronger labor data. Investors cut back expectations for near-term rate cuts.",
                },
                {
                    "title": "Bitcoin holds key support",
                    "source": "Bloomberg",
                    "url": "",
                    "snippet": "Crypto traded sideways after the macro selloff.",
                },
            ],
            "error": None,
        },
        "cio_summary": {"status": "ok", "text": "CIO stays unchanged.", "error": None},
    }
    email = render_digest_email(payload)
    assert "AAPL 254.48 (+1.23%)" in email["text_body"]
    assert "BTC 68078.72 (--)" in email["text_body"]
    assert "(equity" not in email["text_body"]
    assert "(crypto" not in email["text_body"]
    assert "Summary: Treasury yields climbed after stronger labor data. Investors cut back expectations for near-term rate cuts." in email["text_body"]
    assert "Link: https://example.com/fed" in email["text_body"]
    assert "Link: Link unavailable" in email["text_body"]
    assert "CIO Summary" in email["text_body"]
```

- [ ] **Step 2: Add explicit HTML assertions for inline color and clickable links**

```python
assert '<span style="color: #0a7f2e;">+1.23%</span>' in email["html_body"]
assert '<span style="color: #6b7280;">--</span>' in email["html_body"]
assert '<a href="https://example.com/fed">https://example.com/fed</a>' in email["html_body"]
assert "CIO stays unchanged." in email["html_body"]
```

- [ ] **Step 3: Add a fallback-focused render test**

```python
def test_render_digest_email_uses_deterministic_macro_news_fallbacks():
    payload = {
        "meta": {"timezone": "UTC", "scheduled_time": "06:30", "digest_date": "2026-04-08"},
        "technical_sections": [
            {
                "ticker": "ETH",
                "asset_type": "crypto",
                "status": "ok",
                "summary": "unused",
                "trend": "neutral",
                "daily_change_pct": 0.0,
                "indicators": {"last_close": 2076.33},
                "error": None,
            }
        ],
        "macro_news": {
            "status": "ok",
            "summary_points": [],
            "sources": [
                {
                    "title": "Macro headline",
                    "source": "CNBC",
                    "url": None,
                    "snippet": None,
                },
                {
                    "title": "Second headline",
                    "source": "WSJ",
                    "url": "https://example.com/second",
                    "snippet": "Only one sentence here.",
                },
            ],
            "error": None,
        },
        "cio_summary": {"status": "error", "text": "", "error": "llm unavailable"},
    }
    email = render_digest_email(payload)
    assert "ETH 2076.33 (0.00%)" in email["text_body"]
    assert "Summary unavailable from the upstream news feed. This remains a macro watchpoint worth checking in the original article." in email["text_body"]
    assert "Only one sentence here. This remains a macro watchpoint for today's cross-asset risk sentiment." in email["text_body"]
    assert "Unavailable: llm unavailable" in email["text_body"]
```

- [ ] **Step 4: Run the render tests and confirm they fail**

Run: `uv run python -m pytest tests/digest/test_render.py -q`
Expected: FAIL because the current renderer still emits asset-type/trend labels and short macro bullets.

## Chunk 2: Add Daily Change To The Technical Payload

### Task 2: Add payload-contract and generator tests for `daily_change_pct`

**Files:**
- Modify: `tests/digest/test_generator.py`
- Modify: `app/digest/models.py`
- Test: `tests/digest/test_generator.py`

- [ ] **Step 5: Add generator assertions for the new field in fake technical sections**

```python
async def fake_out_of_order_section_builder(ticker: str, run_dir) -> dict[str, object]:
    ...
    return {
        ...
        "daily_change_pct": 1.25 if ticker != "BTC" else -0.5,
        "indicators": {
            "last_close": 1.5,
            "sma_20": 1.4,
            "macd_line": 0.2,
            "macd_signal": 0.1,
            "price_change_pct": 9.9,
        },
        ...
    }
```

- [ ] **Step 6: Add an assertion that every generated section exposes `daily_change_pct`**

```python
for section in payload["technical_sections"]:
    assert "daily_change_pct" in section
```

- [ ] **Step 7: Add a real unit test for technical-section fallback formatting data**

```python
def test_generate_daily_digest_error_section_keeps_daily_change_nullable(...):
    ...
    failing = next(section for section in payload["technical_sections"] if section["ticker"] == "BTC")
    assert failing["daily_change_pct"] is None
```

- [ ] **Step 8: Update `TechnicalSection` to include `daily_change_pct`**

```python
class TechnicalSection(TypedDict, total=False):
    ...
    daily_change_pct: float | None
```

- [ ] **Step 9: Run the generator tests and confirm they fail on missing implementation**

Run: `uv run python -m pytest tests/digest/test_generator.py -q`
Expected: FAIL because `app/digest/technical.py` does not populate `daily_change_pct` yet.

### Task 3: Implement daily-change calculation in the technical adapter

**Files:**
- Modify: `app/digest/technical.py`
- Test: `tests/digest/test_generator.py`

- [ ] **Step 10: Add helper functions for daily change calculation**

```python
def _compute_daily_change_pct(latest_close: float | None, previous_close: float | None) -> float | None:
    if latest_close is None or previous_close in (None, 0):
        return None
    return ((latest_close - previous_close) / previous_close) * 100.0
```

- [ ] **Step 11: For equities, derive daily change from the quant-report indicators payload**

Implementation guidance:
- Inspect whether the quant indicators already expose enough data to compute it directly.
- If not, use the same underlying equity data source in a narrow adapter call to retrieve the latest two closes without changing the generator boundary.
- Do not repurpose the existing `price_change_pct` field, because it is not guaranteed to be single-session.

- [ ] **Step 12: For crypto, derive daily change from the latest two daily closes in the Yahoo-compatible path**

Implementation guidance:
- Keep the crypto adapter on the existing Yahoo-compatible path.
- Use UTC-based daily-candle boundaries consistently.

- [ ] **Step 13: Populate `daily_change_pct` in both success and error sections**

```python
return {
    ...
    "daily_change_pct": computed_change_pct,
    ...
}
```

- [ ] **Step 14: Run the generator tests and confirm they pass**

Run: `uv run python -m pytest tests/digest/test_generator.py -q`
Expected: PASS

## Chunk 3: Implement The New Renderer

### Task 4: Replace the digest email renderer with the approved presentation

**Files:**
- Modify: `app/digest/render.py`
- Test: `tests/digest/test_render.py`

- [ ] **Step 15: Add focused formatting helpers**

Implementation guidance:
- `_format_price(value: float | None) -> str`
- `_format_daily_change_text(value: float | None) -> str`
- `_format_daily_change_html(value: float | None) -> str`
- `_two_sentence_macro_summary(snippet: str | None) -> str`

- [ ] **Step 16: Render the technical overview as a short price board**

Implementation guidance:
- One line per ticker in text.
- One `<li>` per ticker in HTML.
- Use `ticker`, `indicators.last_close`, and `daily_change_pct` only.
- Do not mention `asset_type`, `trend`, or `summary`.

- [ ] **Step 17: Render macro news as 3 detailed items with links**

Implementation guidance:
- Prefer the first 3 items from `macro_news.sources`.
- Render:
  - numbered title
  - `Summary: ...`
  - `Source: ...`
  - `Link: ...`
- When `snippet` is missing, use the exact deterministic fallback string from the spec.
- When `snippet` is one sentence, append the exact deterministic second sentence from the spec.
- When `url` is missing, render `Link unavailable`.

- [ ] **Step 18: Keep CIO rendering logic unchanged**

Implementation guidance:
- Leave the section title and success/error behavior intact.
- Only reposition surrounding content if necessary for readability.

- [ ] **Step 19: Run the render tests and confirm they pass**

Run: `uv run python -m pytest tests/digest/test_render.py -q`
Expected: PASS

## Chunk 4: Verify The Slice And Manually Inspect A Real Email

### Task 5: Verify the digest content-refresh slice

**Files:**
- Modify: `app/digest/models.py`
- Modify: `app/digest/technical.py`
- Modify: `app/digest/render.py`
- Modify: `tests/digest/test_render.py`
- Modify: `tests/digest/test_generator.py`

- [ ] **Step 20: Run the focused digest test slice**

Run: `uv run python -m pytest tests/digest/test_render.py tests/digest/test_generator.py -q`
Expected: PASS

- [ ] **Step 21: Run Ruff on the touched files**

Run: `uv run ruff check app/digest/models.py app/digest/technical.py app/digest/render.py tests/digest/test_render.py tests/digest/test_generator.py`
Expected: PASS

- [ ] **Step 22: Run formatting checks on the touched files**

Run: `uv run ruff format --check app/digest/models.py app/digest/technical.py app/digest/render.py tests/digest/test_render.py tests/digest/test_generator.py`
Expected: PASS

- [ ] **Step 23: Run one real send for manual inspection**

Run:

```bash
uv run python - <<'PY'
import asyncio
from app.tasks.send_daily_digest import send_daily_digest

result = asyncio.run(send_daily_digest())
print(result["email"])
PY
```

Expected:
- email status is `sent` or an explainable environment-specific skip/error
- the rendered email body reflects:
  - compact technical price board
  - detailed macro news with links
  - unchanged CIO section

- [ ] **Step 24: Commit the content refresh**

```bash
git add app/digest/models.py app/digest/technical.py app/digest/render.py tests/digest/test_render.py tests/digest/test_generator.py
git commit -m "feat(digest): refresh email content layout"
```
