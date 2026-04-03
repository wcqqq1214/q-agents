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

