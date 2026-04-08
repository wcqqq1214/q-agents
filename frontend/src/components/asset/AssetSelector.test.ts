import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("./AssetSelector.tsx", import.meta.url),
  "utf8",
);

test("asset selector polls every 300000 ms via shared constant", () => {
  assert.match(source, /STOCK_POLL_INTERVAL_MS/);
  assert.match(source, /300000/);
});

test("asset selector gates visibility refresh with cooldown helper", () => {
  assert.match(source, /canRefreshOnVisibility/);
  assert.match(source, /document\.addEventListener\("visibilitychange"/);
});

test("asset selector cleans up interval and visibility listener", () => {
  assert.match(source, /window\.clearInterval\(interval\)/);
  assert.match(
    source,
    /document\.removeEventListener\("visibilitychange",\s*handleVisibilityChange\)/,
  );
});

test("asset selector interval refresh skips when a request is already in flight", () => {
  assert.match(source, /requestInFlightRef\.current/);
  assert.match(
    source,
    /if\s*\(requestInFlightRef\.current\)\s*\{\s*return;\s*\}/,
  );
});

test("asset selector reports the currently selected stock quote upward", () => {
  assert.match(source, /onSelectedStockQuoteChange/);
  assert.match(
    source,
    /stocks\.find\(\(stock\) => stock\.symbol === selectedAsset\)/,
  );
});

test("asset selector sends the clicked stock quote upward immediately on selection", () => {
  assert.match(source, /onSelectedStockQuoteChange\(stock\)/);
  assert.match(source, /onClick=\{\(\) => handleStockSelect\(stock\)\}/);
});
