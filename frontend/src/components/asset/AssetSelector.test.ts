import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./AssetSelector.tsx", import.meta.url), "utf8");

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

