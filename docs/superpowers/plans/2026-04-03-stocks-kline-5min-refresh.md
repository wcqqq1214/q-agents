# Stocks KLine 5 Minute Refresh Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stock cards and the stock daily K-line refresh on a visible-page 5 minute cadence, keep Yahoo-backed reads off the chart request path, and finalize the daily bar after market close with overwrite semantics.

**Architecture:** Keep stock chart reads database-backed and move freshness control into two places: backend scheduled updates and frontend visible-page polling. On the backend, align quote cache lifetime and scheduler cadence, and make the post-close daily refresh overwrite the same-day partial row. On the frontend, add a shared visibility-refresh guard with cooldown so returning to the tab triggers an immediate refresh without allowing rapid tab switching to spam requests.

**Tech Stack:** Python 3.13, FastAPI, APScheduler, yfinance, pytest, Next.js 16, React 19, TypeScript, Node `node:test`

---

## File Map

- Modify: `app/api/main.py`
- Modify: `app/api/routes/stocks.py`
- Modify: `app/services/stock_updater.py`
- Modify: `app/tasks/update_ohlc.py`
- Modify: `tests/api/test_arq_scheduler.py`
- Add: `tests/test_stock_routes.py`
- Modify: `tests/services/test_stock_updater.py`
- Modify: `tests/tasks/test_update_ohlc.py`
- Add: `frontend/src/lib/visibility-refresh.ts`
- Add: `frontend/src/lib/visibility-refresh.test.ts`
- Modify: `frontend/src/components/asset/AssetSelector.tsx`
- Add: `frontend/src/components/asset/AssetSelector.test.ts`
- Modify: `frontend/src/components/chart/KLineChart.tsx`
- Add: `frontend/src/components/chart/KLineChart.test.ts`

## Chunk 1: Backend Scheduling And Quote Cache

### Task 1: Lock down scheduler cadence with failing tests

**Files:**
- Modify: `tests/api/test_arq_scheduler.py`
- Test: `tests/api/test_arq_scheduler.py`

- [ ] **Step 1: Write the failing test for stock scheduler registration**

```python
def test_configure_market_data_jobs_registers_5_minute_stock_jobs():
    app = FastAPI()
    scheduler = Mock()

    configure_market_data_jobs(app, scheduler)

    intraday_call = next(call for call in scheduler.add_job.call_args_list if call.kwargs["id"] == "intraday_stock_update")
    finalization_call = next(call for call in scheduler.add_job.call_args_list if call.kwargs["id"] == "daily_ohlc_update")

    assert isinstance(intraday_call.kwargs["trigger"], CronTrigger)
    assert str(intraday_call.kwargs["trigger"].timezone) == "America/New_York"
    assert "1,6,11,16,21,26,31,36,41,46,51,56" in str(intraday_call.kwargs["trigger"])

    assert finalization_call.kwargs["hour"] == 16
    assert finalization_call.kwargs["minute"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_arq_scheduler.py -q`
Expected: FAIL because the scheduler setup is inline, the intraday cadence is still 15 minutes, and the post-close job is not explicitly scheduled for `16:30 ET`.

### Task 2: Lock down quote cache TTL with failing tests

**Files:**
- Add: `tests/test_stock_routes.py`
- Test: `tests/test_stock_routes.py`

- [ ] **Step 1: Write the failing cache hit/miss tests**

```python
@pytest.mark.asyncio
async def test_fetch_single_quote_reuses_cache_within_285_seconds():
    _QUOTE_CACHE["AAPL"] = (cached_quote, datetime.now() - timedelta(seconds=100))
    result = await _fetch_single_quote("AAPL")
    assert result is cached_quote


@pytest.mark.asyncio
async def test_fetch_single_quote_refreshes_cache_after_285_seconds():
    _QUOTE_CACHE["AAPL"] = (cached_quote, datetime.now() - timedelta(seconds=286))
    result = await _fetch_single_quote("AAPL")
    assert result.price == 201.0
    assert mock_fetch.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stock_routes.py -q`
Expected: FAIL because the route still uses a 60 second cache TTL.

### Task 3: Implement scheduler helper and cache TTL changes

**Files:**
- Modify: `app/api/main.py`
- Modify: `app/api/routes/stocks.py`
- Test: `tests/api/test_arq_scheduler.py`
- Test: `tests/test_stock_routes.py`

- [ ] **Step 1: Extract stock job registration into a helper**

```python
def configure_market_data_jobs(app: FastAPI, scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        enqueue_daily_ohlc_job,
        "cron",
        hour=16,
        minute=30,
        args=[app],
        id="daily_ohlc_update",
    )
    scheduler.add_job(
        update_stocks_intraday,
        trigger=CronTrigger(
            minute="1,6,11,16,21,26,31,36,41,46,51,56",
            timezone="America/New_York",
        ),
        id="intraday_stock_update",
        replace_existing=True,
        max_instances=1,
    )
```

- [ ] **Step 2: Replace inline scheduler setup with the helper**

```python
configure_market_data_jobs(app, scheduler)
```

- [ ] **Step 3: Change quote cache TTL to 285 seconds**

```python
QUOTE_CACHE_TTL = 285
```

- [ ] **Step 4: Run focused backend tests**

Run: `uv run pytest tests/api/test_arq_scheduler.py tests/test_stock_routes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/main.py app/api/routes/stocks.py tests/api/test_arq_scheduler.py tests/test_stock_routes.py
git commit -m "feat(stocks): align scheduler and quote cache cadence"
```

## Chunk 2: Backend OHLC Finalization And Updater Safety

### Task 4: Write failing tests for post-close overwrite behavior

**Files:**
- Modify: `tests/tasks/test_update_ohlc.py`
- Test: `tests/tasks/test_update_ohlc.py`

- [ ] **Step 1: Add a failing test for overwrite finalization**

```python
@pytest.mark.asyncio
async def test_update_daily_ohlc_uses_overwrite_writer_when_requested():
    with patch("app.tasks.update_ohlc.upsert_ohlc_overwrite", new=Mock()) as mock_overwrite:
        result = await update_daily_ohlc(overwrite_existing=True)
    assert result["success"] == 2
    assert mock_overwrite.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tasks/test_update_ohlc.py -q`
Expected: FAIL because `update_daily_ohlc()` only uses the insert-only writer.

### Task 5: Write failing tests for batched updater behavior

**Files:**
- Modify: `tests/services/test_stock_updater.py`
- Test: `tests/services/test_stock_updater.py`

- [ ] **Step 1: Add a failing regression test that the intraday fetch path stays batched**

```python
def test_fetch_recent_ohlc_batches_requested_symbols_into_one_download():
    with patch("app.services.stock_updater.yf.download", return_value=data) as mock_download:
        fetch_recent_ohlc(["AAPL", "MSFT"], days=5)
    mock_download.assert_called_once()
    assert mock_download.call_args.kwargs["tickers"] == ["AAPL", "MSFT"]
```

- [ ] **Step 2: Run test to verify it fails only if batching regressed**

Run: `uv run pytest tests/services/test_stock_updater.py -q`
Expected: PASS if the current batching behavior is intact; if so, keep the test as a guard before touching update logic.

### Task 6: Implement overwrite-capable finalization

**Files:**
- Modify: `app/tasks/update_ohlc.py`
- Test: `tests/tasks/test_update_ohlc.py`

- [ ] **Step 1: Add an explicit overwrite flag to the daily OHLC task**

```python
async def update_daily_ohlc(
    ctx: Optional[Dict[str, Any]] = None,
    overwrite_existing: bool = False,
) -> Dict[str, int]:
    writer = upsert_ohlc_overwrite if overwrite_existing else upsert_ohlc
```

- [ ] **Step 2: Route all task writes through the selected writer**

```python
await asyncio.to_thread(writer, symbol, data)
```

- [ ] **Step 3: Make the scheduled post-close job request overwrite mode**

```python
await update_daily_ohlc(overwrite_existing=True)
```

- [ ] **Step 4: Run focused backend tests**

Run: `uv run pytest tests/tasks/test_update_ohlc.py tests/services/test_stock_updater.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/tasks/update_ohlc.py tests/tasks/test_update_ohlc.py tests/services/test_stock_updater.py
git commit -m "feat(stocks): finalize daily bars with overwrite semantics"
```

## Chunk 3: Frontend Polling, Visibility Refresh, And Throttle

### Task 7: Add a testable visibility-refresh guard

**Files:**
- Add: `frontend/src/lib/visibility-refresh.ts`
- Add: `frontend/src/lib/visibility-refresh.test.ts`
- Test: `frontend/src/lib/visibility-refresh.test.ts`

- [ ] **Step 1: Write the failing pure-function tests**

```ts
test("canRefreshOnVisibility returns true when enough time has elapsed", () => {
  assert.equal(canRefreshOnVisibility({ now: 61_000, lastRequestStartedAt: 0, inFlight: false }), true);
});

test("canRefreshOnVisibility blocks rapid tab switching within cooldown", () => {
  assert.equal(canRefreshOnVisibility({ now: 20_000, lastRequestStartedAt: 0, inFlight: false }), false);
});

test("canRefreshOnVisibility blocks while a request is already in flight", () => {
  assert.equal(canRefreshOnVisibility({ now: 61_000, lastRequestStartedAt: 0, inFlight: true }), false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/src/lib/visibility-refresh.test.ts`
Expected: FAIL because the helper does not exist yet.

### Task 8: Wire stock cards to 5 minute polling plus visibility cooldown

**Files:**
- Modify: `frontend/src/components/asset/AssetSelector.tsx`
- Add: `frontend/src/components/asset/AssetSelector.test.ts`
- Modify: `frontend/src/lib/visibility-refresh.ts`
- Test: `frontend/src/components/asset/AssetSelector.test.ts`
- Test: `frontend/src/lib/visibility-refresh.test.ts`

- [ ] **Step 1: Write the failing source-level card polling tests**

```ts
test("asset selector polls every 300000 ms", () => {
  assert.match(source, /300000/);
});

test("asset selector uses visibility refresh guard before refreshing on tab return", () => {
  assert.match(source, /canRefreshOnVisibility/);
  assert.match(source, /visibilitychange/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test frontend/src/lib/visibility-refresh.test.ts frontend/src/components/asset/AssetSelector.test.ts`
Expected: FAIL because the component still polls every 120000 ms and has no cooldown guard.

- [ ] **Step 3: Implement the shared helper**

```ts
export const STOCK_POLL_INTERVAL_MS = 300_000;
export const VISIBILITY_REFRESH_COOLDOWN_MS = 60_000;

export function canRefreshOnVisibility(input: {
  now: number;
  lastRequestStartedAt: number | null;
  inFlight: boolean;
  cooldownMs?: number;
}): boolean {
  if (input.inFlight) return false;
  if (input.lastRequestStartedAt == null) return true;
  return input.now - input.lastRequestStartedAt >= (input.cooldownMs ?? VISIBILITY_REFRESH_COOLDOWN_MS);
}
```

- [ ] **Step 4: Update `AssetSelector` to use 5 minute cadence and cooldown**

```ts
const lastRequestStartedAtRef = useRef<number | null>(null);
const requestInFlightRef = useRef(false);

const fetchQuotes = useCallback(async (isManual = false) => {
  lastRequestStartedAtRef.current = Date.now();
  requestInFlightRef.current = true;
  try {
    ...
  } finally {
    requestInFlightRef.current = false;
  }
}, [...]);
```

- [ ] **Step 5: Run focused frontend tests**

Run: `node --test frontend/src/lib/visibility-refresh.test.ts frontend/src/components/asset/AssetSelector.test.ts`
Expected: PASS

### Task 9: Wire stock K-line to 5 minute polling plus visibility cooldown

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx`
- Add: `frontend/src/components/chart/KLineChart.test.ts`
- Modify: `frontend/src/lib/visibility-refresh.ts`
- Test: `frontend/src/components/chart/KLineChart.test.ts`

- [ ] **Step 1: Write the failing source-level K-line tests**

```ts
test("k line chart registers 5 minute polling for stocks", () => {
  assert.match(source, /setInterval/);
  assert.match(source, /300000/);
});

test("k line chart refreshes immediately on visibilitychange with cooldown guard", () => {
  assert.match(source, /canRefreshOnVisibility/);
  assert.match(source, /document\.addEventListener\("visibilitychange"/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/src/components/chart/KLineChart.test.ts`
Expected: FAIL because the chart has no polling effect and no visibility-return refresh logic.

- [ ] **Step 3: Implement stock-only polling in `KLineChart`**

```ts
useEffect(() => {
  if (assetType !== "stocks" || !selectedStock) return;
  ...
  const interval = window.setInterval(() => {
    if (document.visibilityState === "visible") void fetchData();
  }, STOCK_POLL_INTERVAL_MS);
  ...
}, [assetType, selectedStock, fetchData]);
```

- [ ] **Step 4: Guard visibility-return refreshes and preserve existing chart data on failure**

```ts
const [error, setError] = useState<string | null>(null);
const lastRequestStartedAtRef = useRef<number | null>(null);
const requestInFlightRef = useRef(false);

if (!canRefreshOnVisibility(...)) return;
void fetchData();
```

- [ ] **Step 5: Run focused frontend tests**

Run: `node --test frontend/src/components/chart/KLineChart.test.ts frontend/src/lib/visibility-refresh.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/visibility-refresh.ts frontend/src/lib/visibility-refresh.test.ts frontend/src/components/asset/AssetSelector.tsx frontend/src/components/asset/AssetSelector.test.ts frontend/src/components/chart/KLineChart.tsx frontend/src/components/chart/KLineChart.test.ts
git commit -m "feat(frontend): refresh stock cards and k line every five minutes"
```

## Chunk 4: Verification

### Task 10: Run targeted verification

**Files:**
- Test: `tests/api/test_arq_scheduler.py`
- Test: `tests/test_stock_routes.py`
- Test: `tests/tasks/test_update_ohlc.py`
- Test: `tests/services/test_stock_updater.py`
- Test: `frontend/src/lib/visibility-refresh.test.ts`
- Test: `frontend/src/components/asset/AssetSelector.test.ts`
- Test: `frontend/src/components/chart/KLineChart.test.ts`

- [ ] **Step 1: Run backend regression tests**

Run: `uv run pytest tests/api/test_arq_scheduler.py tests/test_stock_routes.py tests/tasks/test_update_ohlc.py tests/services/test_stock_updater.py -q`
Expected: PASS

- [ ] **Step 2: Run frontend node tests**

Run: `node --test frontend/src/lib/visibility-refresh.test.ts frontend/src/components/asset/AssetSelector.test.ts frontend/src/components/chart/KLineChart.test.ts`
Expected: PASS

- [ ] **Step 3: Run frontend type check**

Run: `cd frontend && pnpm type-check`
Expected: PASS

- [ ] **Step 4: Run frontend lint**

Run: `cd frontend && pnpm lint`
Expected: PASS

- [ ] **Step 5: Review final diff for scope control**

Run: `git diff -- app/api/main.py app/api/routes/stocks.py app/tasks/update_ohlc.py app/services/stock_updater.py tests/api/test_arq_scheduler.py tests/test_stock_routes.py tests/tasks/test_update_ohlc.py tests/services/test_stock_updater.py frontend/src/lib/visibility-refresh.ts frontend/src/lib/visibility-refresh.test.ts frontend/src/components/asset/AssetSelector.tsx frontend/src/components/asset/AssetSelector.test.ts frontend/src/components/chart/KLineChart.tsx frontend/src/components/chart/KLineChart.test.ts`
Expected: Only the stock 5 minute cadence, visibility guard, quote TTL, and post-close finalization changes are present.
