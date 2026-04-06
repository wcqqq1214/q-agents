# Frontend Settings Display Preferences Only Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove frontend API-key-management behavior from `/settings` while keeping the existing display-preference toggle and its `localStorage` persistence unchanged.

**Architecture:** Keep the change localized to the frontend settings page and shared frontend API surface. First add a regression test that fails on the current API-key-management UI and helper exports, then delete the page logic and frontend interfaces, and finish with targeted frontend verification.

**Tech Stack:** Next.js 16, React 19, TypeScript, Node `node:test`, ESLint

---

## Chunk 1: Remove Frontend Settings API Configuration

### Task 1: Lock the desired settings-page behavior with a failing regression test

**Files:**
- Create: `frontend/src/app/settings/page.test.ts`
- Test: `frontend/src/app/settings/page.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
test("settings page keeps display preferences but removes api key management copy", () => {
  // Assert display-preference copy remains.
  // Assert API key labels and save button copy are absent.
});

test("settings page no longer calls frontend settings api helpers", () => {
  // Assert the page source does not reference api.getSettings/updateSettings.
});

test("frontend api client and shared types no longer expose settings interfaces", () => {
  // Assert api.ts and types.ts do not export settings-specific helpers or types.
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --experimental-strip-types frontend/src/app/settings/page.test.ts`
Expected: FAIL because the current page still renders API key configuration copy and still references `api.getSettings()` / `api.updateSettings()` and settings types.

### Task 2: Remove frontend settings API helpers and types

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Test: `frontend/src/app/settings/page.test.ts`

- [ ] **Step 3: Write minimal implementation**

```ts
// Remove SettingsRequest / SettingsResponse imports and types.
// Remove api.getSettings and api.updateSettings helpers.
```

- [ ] **Step 4: Run the regression test**

Run: `node --test --experimental-strip-types frontend/src/app/settings/page.test.ts`
Expected: Still FAIL because the page itself still renders API key management content and logic.

### Task 3: Simplify the settings page to display preferences only

**Files:**
- Modify: `frontend/src/app/settings/page.tsx`
- Test: `frontend/src/app/settings/page.test.ts`

- [ ] **Step 5: Write minimal implementation**

```tsx
export default function SettingsPage() {
  const { trendMode, setTrendMode, isMounted } = useTrendColor();

  return (
    // Render only page title/copy plus the display-preferences card.
    // Keep the existing Switch behavior for trend-mode toggling.
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `node --test --experimental-strip-types frontend/src/app/settings/page.test.ts`
Expected: PASS

### Task 4: Verify the touched frontend slice

**Files:**
- Modify: `frontend/src/app/settings/page.test.ts`
- Modify: `frontend/src/app/settings/page.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`

- [ ] **Step 7: Run the existing frontend node tests plus the new regression**

Run: `node --test --experimental-strip-types frontend/src/app/settings/page.test.ts frontend/src/components/asset/AssetSelector.test.ts frontend/src/components/chart/KLineChart.test.ts frontend/src/components/chat/MarkdownRenderer.test.ts frontend/src/components/reports/ReportCard.test.ts frontend/src/lib/visibility-refresh.test.ts`
Expected: PASS

- [ ] **Step 8: Run lint**

Run: `cd frontend && pnpm lint`
Expected: PASS with no new errors; existing unrelated warnings may remain if unchanged.

- [ ] **Step 9: Run type checking**

Run: `cd frontend && pnpm type-check`
Expected: PASS
