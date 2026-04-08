# Stock K-Line Quote Fallback Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synthesize the current America/New_York market-day stock candle from live quote data when daily history is still stale.

**Architecture:** History refresh remains the primary source of daily stock OHLC, but a quote-derived temporary candle fills the current trading day when history lags. The updater writes that row to the DB, and the route can also heal stale reads with the same logic.

**Tech Stack:** FastAPI, Python 3.13, pytest, Ruff, MCP market-data client

---

### Task 1: Add failing regression tests

**Files:**
- Modify: `tests/services/test_stock_updater.py`
- Modify: `tests/api/test_stock_ohlc_route.py`

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Run `uv run pytest tests/services/test_stock_updater.py tests/api/test_stock_ohlc_route.py -q` and confirm failure**
- [ ] **Step 3: Implement minimal quote-based fallback**
- [ ] **Step 4: Re-run `uv run pytest tests/services/test_stock_updater.py tests/api/test_stock_ohlc_route.py -q` and confirm pass**

### Task 2: Verify and integrate

**Files:**
- Modify: `app/services/stock_updater.py`
- Modify: `app/api/routes/ohlc.py`

- [ ] **Step 1: Run `uv run pytest tests/services/test_stock_updater.py tests/api/test_stock_ohlc_route.py tests/test_stock_routes.py -q`**
- [ ] **Step 2: Run `bash .agents/skills/auto-dev-workflow/scripts/run_scoped_checks.sh --base-sha 03712e9230c6b882195304ccb6782f2f6b269e7d --diff-target worktree --cmd 'uv run pytest tests/services/test_stock_updater.py tests/api/test_stock_ohlc_route.py tests/test_stock_routes.py -q'`**
- [ ] **Step 3: Commit and run `bash .agents/skills/auto-dev-workflow/scripts/run_final_gate.sh --base-sha 03712e9230c6b882195304ccb6782f2f6b269e7d`**
