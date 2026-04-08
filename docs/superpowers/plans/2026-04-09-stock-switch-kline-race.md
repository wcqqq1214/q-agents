# Stock Switch K-Line Race Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale stock OHLC responses and stale selected quotes from corrupting the currently selected stock chart during rapid switching.

**Architecture:** Keep the fix frontend-local. Introduce a tiny latest-only request gate utility, wire it into `KLineChart` so stale responses cannot win, and make `AssetSelector` synchronously lift the clicked stock quote before the selection effect catches up.

**Tech Stack:** Next.js 16, React 19, TypeScript, Node test runner

---

## Chunk 1: Frontend Race Fix

### Task 1: Guard the chart against stale OHLC responses

**Files:**
- Create: `frontend/src/lib/latest-only-request.ts`
- Test: `frontend/src/lib/latest-only-request.test.ts`
- Modify: `frontend/src/components/chart/KLineChart.tsx`
- Test: `frontend/src/components/chart/KLineChart.test.ts`

- [x] **Step 1: Write the failing tests**

Add a pure Node test for a latest-only request gate and extend `KLineChart.test.ts` to require that the chart starts a tracked request and ignores stale responses.

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test src/lib/latest-only-request.test.ts src/components/chart/KLineChart.test.ts`
Expected: FAIL because the gate module does not exist yet and the chart source does not reference request gating.

- [x] **Step 3: Write minimal implementation**

Create a small request gate utility with `begin()`, `invalidate()`, and `isCurrent()`. In `KLineChart`, use a ref-backed gate, invalidate it on stock changes, clear stale chart data, and ignore stale success/error/finally branches.

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test src/lib/latest-only-request.test.ts src/components/chart/KLineChart.test.ts`
Expected: PASS

### Task 2: Keep the clicked stock quote aligned with the selected card

**Files:**
- Modify: `frontend/src/components/asset/AssetSelector.tsx`
- Test: `frontend/src/components/asset/AssetSelector.test.ts`

- [x] **Step 1: Write the failing test**

Extend `AssetSelector.test.ts` so it requires the clicked stock quote to be sent upward immediately on selection.

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test src/components/asset/AssetSelector.test.ts`
Expected: FAIL because selection currently only reports the quote through the later effect.

- [x] **Step 3: Write minimal implementation**

Add explicit stock and crypto selection handlers. The stock handler should synchronously call `onSelectedStockQuoteChange(stock)` before `onAssetSelect(stock.symbol)`.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd frontend && node --test src/lib/latest-only-request.test.ts src/components/chart/KLineChart.test.ts src/components/asset/AssetSelector.test.ts src/app/page.test.ts`
Expected: PASS

- [x] **Step 5: Run scoped checks**

Run: `bash .agents/skills/auto-dev-workflow/scripts/run_scoped_checks.sh --base-sha 3b856ebbd0ed103efe0750bf978b8047c887d080 --diff-target worktree --cmd 'cd frontend && node --test src/lib/latest-only-request.test.ts src/components/chart/KLineChart.test.ts src/components/asset/AssetSelector.test.ts src/app/page.test.ts'`
Expected: PASS, with only the pre-existing `frontend/src/hooks/use-toast.ts` unused-vars warning.
