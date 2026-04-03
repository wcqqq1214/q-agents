import assert from "node:assert/strict";
import test from "node:test";

async function loadModule() {
  const moduleUrl = new URL("./visibility-refresh.ts", import.meta.url).href;
  return import(moduleUrl);
}

test("visibility refresh constants are aligned to 5m polling and cooldown", async () => {
  const { STOCK_POLL_INTERVAL_MS, VISIBILITY_REFRESH_COOLDOWN_MS } =
    await loadModule();
  assert.equal(STOCK_POLL_INTERVAL_MS, 300000);
  assert.equal(VISIBILITY_REFRESH_COOLDOWN_MS, 60000);
});

test("canRefreshOnVisibility allows first refresh when no prior request exists", async () => {
  const { canRefreshOnVisibility } = await loadModule();
  const allowed = canRefreshOnVisibility({
    now: 61000,
    lastRequestStartedAt: null,
    inFlight: false,
  });

  assert.equal(allowed, true);
});

test("canRefreshOnVisibility blocks refresh while request is in flight", async () => {
  const { canRefreshOnVisibility } = await loadModule();
  const allowed = canRefreshOnVisibility({
    now: 61000,
    lastRequestStartedAt: 0,
    inFlight: true,
  });

  assert.equal(allowed, false);
});

test("canRefreshOnVisibility blocks refresh inside cooldown window", async () => {
  const { canRefreshOnVisibility } = await loadModule();
  const allowed = canRefreshOnVisibility({
    now: 20000,
    lastRequestStartedAt: 0,
    inFlight: false,
  });

  assert.equal(allowed, false);
});

test("canRefreshOnVisibility allows refresh after cooldown window", async () => {
  const { canRefreshOnVisibility } = await loadModule();
  const allowed = canRefreshOnVisibility({
    now: 61000,
    lastRequestStartedAt: 0,
    inFlight: false,
  });

  assert.equal(allowed, true);
});
