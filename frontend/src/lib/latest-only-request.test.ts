import assert from "node:assert/strict";
import test from "node:test";

async function loadModule() {
  const moduleUrl = new URL("./latest-only-request.ts", import.meta.url).href;
  return import(moduleUrl);
}

test("latest-only request gate only accepts the newest started request", async () => {
  const { createLatestOnlyRequestGate } = await loadModule();
  const gate = createLatestOnlyRequestGate();

  const firstRequest = gate.begin();
  const secondRequest = gate.begin();

  assert.equal(gate.isCurrent(firstRequest), false);
  assert.equal(gate.isCurrent(secondRequest), true);
});

test("latest-only request gate invalidates older requests when selection changes", async () => {
  const { createLatestOnlyRequestGate } = await loadModule();
  const gate = createLatestOnlyRequestGate();

  const requestId = gate.begin();
  gate.invalidate();

  assert.equal(gate.isCurrent(requestId), false);
});
