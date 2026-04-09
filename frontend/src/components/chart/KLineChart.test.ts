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

test("k line chart chart-update effect tracks timeRange and current-data ownership in dependencies", () => {
  assert.match(
    source,
    /\},\s*\[\s*assetType,\s*hasCurrentOhlcData,\s*liveQuote,\s*ohlcData,\s*resolvedTheme,\s*trendMode,\s*timeRange,\s*\]\s*\);/,
  );
});

test("k line chart only shows blocking error state when no data exists", () => {
  assert.doesNotMatch(source, /if\s*\(error\)\s*\{/);
  assert.match(
    source,
    /if\s*\(error\s*&&\s*visibleOhlcData\.length\s*===\s*0\)\s*\{/,
  );
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
  assert.match(source, /liveQuote\?\.price == null/);
});

test("k line chart ignores stale OHLC responses after a newer request starts", () => {
  assert.match(source, /createLatestOnlyRequestGate/);
  assert.match(source, /const requestId = requestGateRef\.current\.begin\(\)/);
  assert.match(
    source,
    /if\s*\(!requestGateRef\.current\.isCurrent\(requestId\)\)\s*\{\s*return;\s*\}/,
  );
});

test("k line chart delegates latest stock legend percent to quote-aware legend metrics", () => {
  assert.match(source, /resolveLegendChangeMetrics/);
  assert.match(source, /hoveredTime:\s*param\.time/);
  assert.match(source, /latestDateString,/);
  assert.match(source, /previousClose:/);
  assert.match(source, /liveQuote,\s*currentUsMarketDate/);
  assert.doesNotMatch(source, /legendLabel/);
});

test("k line chart clears stale legend content while loading or when no data is available", () => {
  assert.match(
    source,
    /const\s+shouldHideChartSurface\s*=\s*isChartLoading\s*\|\|\s*visibleOhlcData\.length\s*===\s*0/,
  );
  assert.match(source, /if\s*\(shouldHideChartSurface\)\s*\{/);
  assert.match(source, /legend\.style\.display\s*=\s*"none"/);
  assert.match(source, /legend\.innerHTML\s*=\s*""/);
  assert.match(
    source,
    /style=\{\s*shouldHideChartSurface\s*\?\s*\{\s*display:\s*"none"\s*\}\s*:\s*undefined\s*\}/,
  );
});

test("k line chart only treats OHLC data as current when it matches the selected stock", () => {
  assert.match(
    source,
    /const\s+\[ohlcSymbol,\s*setOhlcSymbol\]\s*=\s*useState<string \| null>\(null\)/,
  );
  assert.match(
    source,
    /const\s+hasCurrentOhlcData\s*=\s*selectedStock\s*!==\s*null\s*&&\s*ohlcSymbol\s*===\s*selectedStock/,
  );
  assert.match(
    source,
    /const\s+visibleOhlcData\s*=\s*hasCurrentOhlcData\s*\?\s*ohlcData\s*:\s*\[\]/,
  );
});

test("k line chart hides the stale chart canvas until current symbol data is ready", () => {
  assert.match(source, /import\s+\{\s*cn\s*\}\s+from\s+"@\/lib\/utils"/);
  assert.match(
    source,
    /className=\{cn\(\s*"absolute inset-0",\s*shouldHideChartSurface\s*&&\s*"invisible",?\s*\)\}/,
  );
});
