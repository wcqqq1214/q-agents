import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./KLineChart.tsx", import.meta.url), "utf8");

test("k line chart registers stock polling with 5 minute interval", () => {
  assert.match(source, /STOCK_POLL_INTERVAL_MS/);
  assert.match(source, /setInterval/);
  assert.match(source, /300000/);
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
    /\},\s*\[ohlcData,\s*resolvedTheme,\s*trendMode,\s*timeRange\]\s*\);/,
  );
});

test("k line chart only shows blocking error state when no data exists", () => {
  assert.doesNotMatch(source, /if\s*\(error\)\s*\{/);
  assert.match(source, /if\s*\(error\s*&&\s*ohlcData\.length\s*===\s*0\)\s*\{/);
});
