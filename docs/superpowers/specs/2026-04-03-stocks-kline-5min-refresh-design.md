# Stocks KLine 5 Minute Refresh Design

## Summary

Make stock quote cards and the stock daily K-line chart refresh on a consistent 5 minute cadence during market hours without introducing WebSocket infrastructure. Keep the frontend on API polling, keep the stock OHLC API database-backed, and move intraday stock database refresh from 15 minutes to 5 minutes so the current trading day's candle stays reasonably fresh.

## Goals

- Keep stock `card` refresh and stock K-line refresh aligned at 5 minutes.
- Show the current trading day's partial daily candle on the stock chart during market hours.
- Avoid request-path calls from the stock chart directly to Yahoo Finance.
- Reduce the chance of `yfinance` rate limiting compared with a more aggressive 2 minute design.
- Preserve the current architecture shape: frontend -> backend API -> local database / scheduled updater.

## Non-Goals

- No WebSocket or SSE market-data push for stock cards or stock K-lines.
- No second-level or tick-level streaming updates.
- No new market data vendor integration.
- No redesign of the chart or asset card UI.
- No dynamic backoff scheduler in this iteration unless already required by implementation details.

## Current State

### Frontend

- `frontend/src/components/asset/AssetSelector.tsx` polls stock cards every 2 minutes.
- `frontend/src/components/chart/KLineChart.tsx` fetches stock OHLC only on selection/range changes and does not auto-refresh.

### Backend

- `app/api/routes/stocks.py` serves stock quotes and caches quote responses for 60 seconds.
- `app/api/routes/ohlc.py` serves stock OHLC data from the local database only.
- `app/api/main.py` schedules stock intraday updates every 15 minutes during US trading hours.
- `app/services/stock_updater.py` fetches recent daily OHLC from `yfinance` and overwrites existing same-day rows so the partial daily candle can be refreshed in place.
- `app/tasks/update_ohlc.py` already runs after market close, but its current insert-only write path does not guarantee replacement of an existing same-day partial row.

## Proposed Approach

Use the existing polling-plus-database architecture and align all stock-refresh cadences to 5 minutes.

1. The frontend stock cards poll every 5 minutes when the page is visible.
2. The stock K-line chart also polls every 5 minutes when the page is visible.
3. The backend intraday stock updater runs every 5 minutes during market hours.
4. The stock quote cache TTL is raised close to, but slightly below, 5 minutes so frontend polling does not repeatedly hit a still-valid stale cache entry.
5. The stock OHLC API remains database-backed and does not fetch Yahoo data inline for user requests.

This keeps user traffic off Yahoo for chart refreshes, keeps the current daily candle fresh enough for UI display, and avoids the complexity of live push infrastructure.

## Architecture

### Unit 1: Frontend stock card cadence alignment

Responsibility:
- Refresh stock cards every 5 minutes instead of every 2 minutes.

Files:
- `frontend/src/components/asset/AssetSelector.tsx`

Behavior:
- Change the stock/crypto refresh interval constant from 120000 ms to 300000 ms.
- Keep the existing visibility-gated polling behavior.
- Keep the immediate refresh on `visibilitychange` when the page becomes visible again.
- Keep manual refresh unchanged.

### Unit 2: Frontend K-line polling

Responsibility:
- Refresh the selected stock chart on the same 5 minute cadence used by stock cards.

Files:
- `frontend/src/components/chart/KLineChart.tsx`

Behavior:
- Keep the current fetch-on-selection/range-change behavior.
- Add a visibility-gated 5 minute polling effect for stock charts.
- Add an immediate refresh when the document becomes visible again after being hidden.
- Do not introduce polling for crypto as part of this stock-specific change unless needed for shared code simplicity.
- On polling failure, preserve the currently rendered chart data instead of clearing it.

### Unit 3: Backend stock quote cache alignment

Responsibility:
- Match quote cache lifetime to the new 5 minute frontend cadence.

Files:
- `app/api/routes/stocks.py`

Behavior:
- Raise `QUOTE_CACHE_TTL` from 60 seconds to 285 seconds.
- Keep the current symbol-level cache behavior.
- Continue returning cached quote payloads when valid.

### Unit 4: Backend intraday stock updater cadence

Responsibility:
- Refresh the current day's partial OHLC row every 5 minutes during market hours.

Files:
- `app/api/main.py`
- `app/services/stock_updater.py`

Behavior:
- Change the APScheduler cron cadence from every 15 minutes to every 5 minutes.
- Keep existing market-hours and holiday gating.
- Continue fetching recent daily OHLC in a single batched `yfinance.download(tickers=[...])` call for the intraday updater path, and overwrite same-day rows in the database.
- Do not add user-request-triggered yfinance fetches to compensate for missing scheduled updates.
- Keep a post-close stock finalization job, but require it to overwrite the same-day row rather than relying on insert-only behavior.

### Unit 5: Database-backed stock OHLC stays authoritative

Responsibility:
- Preserve the current backend contract where chart reads come from the local database.

Files:
- `app/api/routes/ohlc.py`
- `app/database/ohlc.py`

Behavior:
- No contract change for `GET /api/stocks/{symbol}/ohlc`.
- Continue using overwrite semantics for same-day rows so the latest partial candle replaces the previous version.

## Data Flow

### Stock cards

1. User opens the page.
2. Frontend requests `/api/stocks/quotes`.
3. Backend returns cached quotes when within TTL; otherwise fetches fresh quotes via the existing Yahoo-backed MCP path.
4. If the page becomes visible again, frontend immediately refreshes quotes.
5. Frontend repeats polling every 5 minutes while the document is visible.

### Stock K-line chart

1. User selects a stock or changes the time range.
2. Frontend requests `/api/stocks/{symbol}/ohlc`.
3. Backend reads OHLC rows from the local database.
4. During market hours, the scheduler refreshes the latest daily stock rows every 5 minutes.
5. If the page becomes visible again, frontend immediately refreshes chart data.
6. Frontend re-fetches every 5 minutes while visible, so the latest partial daily candle appears without page reload.
7. After market close, a stock finalization job refreshes the final bar again using overwrite semantics so the stored end-of-day candle is corrected even when a partial same-day row already exists.

## Error Handling

### Frontend

- Stock card polling failures must not crash the page.
- K-line polling failures must not clear already-rendered OHLC data.
- Keep current toast behavior unless implementation requires a more targeted adjustment.

### Backend

- If `yfinance` fails or rate-limits during an intraday refresh, keep the last successful database row.
- Do not overwrite OHLC rows with empty or partial-invalid results.
- Keep scheduled update failure isolated to that run; the next scheduled refresh should retry naturally.
- The post-close finalization path must be able to replace the same trading day's partial row with the final daily bar.
- Quote fetch failures should keep current per-symbol error handling behavior.

## Rate Limit Considerations

- This design is intentionally less aggressive than a 2 minute schedule.
- Stock chart refreshes do not directly hit Yahoo because they read from the local database.
- Yahoo exposure remains concentrated in:
  - the scheduled stock updater
  - the stock quote endpoint when cache expires
- Setting quote cache TTL to 285 seconds avoids a symmetric 300 second poll / 300 second TTL race where a client can hit a still-valid stale cache entry and then wait another full poll interval.
- The intraday stock updater should continue using the existing batched `yfinance.download(tickers=[...])` path rather than per-symbol loops for the live 5 minute refresh job.
- A similar boundary race can still exist between chart polling and the 5 minute OHLC scheduler. This design accepts that residual jitter rather than adding push delivery or a shorter client poll cadence.
- If later observation shows `YFRateLimitError` or similar upstream throttling, a follow-up change can introduce temporary scheduler backoff. That is not part of this initial implementation scope.

## Testing Strategy

Implementation must follow TDD.

### Backend tests

- Red-green test for quote cache TTL behavior where repeated requests within 285 seconds reuse cached data.
- Red-green test for quote cache expiry behavior where a request after 285 seconds triggers a fresh upstream read.
- Red-green test for intraday overwrite behavior so the same trading date is updated rather than duplicated.
- Red-green test for scheduled stock update logic preserving previous data when fresh fetch returns nothing or errors.
- Red-green test for the intraday updater path keeping batched symbol fetches rather than regressing to per-symbol pull loops.
- Red-green test for post-close stock finalization overwriting an existing same-day partial row with the final daily bar.

### Frontend tests

- Red-green test for stock chart polling setup:
  - initial fetch still happens on mount / dependency change
  - a 5 minute interval is registered for stock charts
  - polling respects document visibility behavior
  - becoming visible triggers an immediate refresh
- Red-green test for stock card polling cadence change from 2 minutes to 5 minutes.
- Red-green test for stock card visibility recovery where tab focus triggers an immediate refresh.

### Manual verification

- Start the API and frontend during US market hours.
- Confirm stock cards refresh on a 5 minute visible-page cadence.
- Confirm stock daily K-line refreshes on the same cadence.
- Confirm the current day's daily candle changes after a successful backend intraday refresh.
- Confirm a temporary Yahoo failure does not blank the chart.

## Risks

- `yfinance` is still an unofficial upstream and may rate-limit unpredictably even at moderate cadence.
- A 5 minute chart cadence will not feel truly real-time; it is a deliberate trade-off for stability and implementation simplicity.
- If the frontend polls more often than the backend updates due to misconfiguration, the UI can appear stale despite visible refresh activity. Cadence alignment tests should cover this.

## Acceptance Criteria

- Stock cards refresh every 5 minutes while the page is visible.
- Stock K-line chart refreshes every 5 minutes while the page is visible.
- Backend intraday stock updater runs every 5 minutes during valid market hours.
- Stock quote cache TTL is 285 seconds.
- Stock chart requests remain database-backed and do not introduce inline Yahoo fetches.
- The current day's partial daily candle can update intraday without a full page reload.
- Returning to a previously hidden page triggers an immediate stock card and stock K-line refresh.
- A post-close stock finalization job refreshes the final daily bar after market close using overwrite semantics.
