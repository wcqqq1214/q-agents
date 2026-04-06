import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const settingsPageSource = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../../lib/api.ts", import.meta.url), "utf8");
const typesSource = readFileSync(new URL("../../lib/types.ts", import.meta.url), "utf8");

test("settings page keeps display preferences but removes api key management copy", () => {
  assert.match(settingsPageSource, /Display Preferences/);
  assert.match(settingsPageSource, /Price Color Convention/);

  assert.doesNotMatch(settingsPageSource, /Claude API Key/);
  assert.doesNotMatch(settingsPageSource, /OpenAI API Key/);
  assert.doesNotMatch(settingsPageSource, /Polygon API Key/);
  assert.doesNotMatch(settingsPageSource, /Tavily API Key/);
  assert.doesNotMatch(settingsPageSource, /Save Configuration/);
});

test("settings page no longer calls frontend settings api helpers", () => {
  assert.doesNotMatch(settingsPageSource, /api\.getSettings\(/);
  assert.doesNotMatch(settingsPageSource, /api\.updateSettings\(/);
});

test("frontend api client and shared types no longer expose settings interfaces", () => {
  assert.doesNotMatch(apiSource, /getSettings:\s*\(\)/);
  assert.doesNotMatch(apiSource, /updateSettings:\s*\(data:/);
  assert.doesNotMatch(typesSource, /export interface SettingsResponse/);
  assert.doesNotMatch(typesSource, /export interface SettingsRequest/);
});
