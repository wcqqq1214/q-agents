import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("./KLineChart.tsx", import.meta.url),
  "utf8",
);

test("k line chart registers stock polling with 5 minute interval", () => {
  assert.match(source, /STOCK_POLL_INTERVAL_MS/);
  assert.match(source, /setInterval/);
  assert.match(source, /300000/);
});

test("k line chart polling is explicitly guarded to stocks only", () => {
  assert.match(
    source,
    /if\s*\(assetType\s*!==\s*"stocks"\s*\|\|\s*!selectedStock\)\s*\{/,
  );
});

test("k line chart gates visibility refresh with cooldown helper", () => {
  assert.match(source, /canRefreshOnVisibility/);
  assert.match(source, /document\.addEventListener\("visibilitychange"/);
});

test("k line chart cleans up interval and visibility listener", () => {
  assert.match(source, /window\.clearInterval\(interval\)/);
  assert.match(
    source,
    /document\.removeEventListener\("visibilitychange",\s*handleVisibilityChange\)/,
  );
});

test("k line chart chart-update effect tracks timeRange in dependencies", () => {
  // ESLint warning in repo indicates the chart-update effect reads timeRange; ensure deps include it.
  assert.match(
    source,
    /\},\s*\[assetType,\s*liveQuote,\s*ohlcData,\s*resolvedTheme,\s*trendMode,\s*timeRange\]\s*\);/,
  );
});

test("k line chart only shows blocking error state when no data exists", () => {
  assert.doesNotMatch(source, /if\s*\(error\)\s*\{/);
  assert.match(source, /if\s*\(error\s*&&\s*ohlcData\.length\s*===\s*0\)\s*\{/);
});

test("k line chart auto-refresh skips when a request is already in flight", () => {
  assert.match(source, /requestInFlightRef\.current/);
  assert.match(
    source,
    /if\s*\(requestInFlightRef\.current\)\s*\{\s*return;\s*\}/,
  );
});

test("k line chart suppresses auto-refresh toast noise once data exists", () => {
  assert.match(
    source,
    /const\s+shouldToast\s*=\s*!isAutoRefresh\s*\|\|\s*latestOhlcDataRef\.current\.length\s*===\s*0/,
  );
  assert.match(source, /if\s*\(shouldToast\)\s*\{\s*toast\(/);
  assert.match(source, /void fetchData\(true\)/);
});

test("k line chart can overlay the selected stock live quote onto the latest bar", () => {
  assert.match(source, /liveQuote\?: StockInfo \| null/);
  assert.match(source, /mergeLiveQuoteIntoLatestStockBar/);
  assert.match(source, /liveQuote\.price/);
});

test("k line chart ignores stale OHLC responses after a newer request starts", () => {
  assert.match(source, /createLatestOnlyRequestGate/);
  assert.match(source, /const requestId = requestGateRef\.current\.begin\(\)/);
  assert.match(
    source,
    /if\s*\(!requestGateRef\.current\.isCurrent\(requestId\)\)\s*\{\s*return;\s*\}/,
  );
});
