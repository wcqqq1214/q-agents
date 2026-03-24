# Crypto K-Line Timezone Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display crypto K-line chart times in user's browser local timezone instead of UTC

**Architecture:** Frontend-only changes to KLineChart component. Add custom time formatter to lightweight-charts config and timezone indicator UI. Backend continues returning UTC timestamps.

**Tech Stack:** React, TypeScript, lightweight-charts, Next.js

**Spec Document:** `docs/superpowers/specs/2026-03-23-crypto-kline-timezone-adaptation-design.md`

---

## File Structure

**Modified Files:**
- `frontend/src/components/chart/KLineChart.tsx` - Add timezone formatting and indicator UI

**No New Files Created**

---

## Task 1: Add Timezone Helper Function

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:67`

- [ ] **Step 1: Add timezone info helper function**

Add this function after the `calculateDateRange` function (after line 66, before line 67):

```typescript
// Helper function to get current timezone information
function getTimezoneInfo(): { name: string; offset: string } {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const offsetMinutes = -new Date().getTimezoneOffset();
  const offsetHours = offsetMinutes / 60;
  const offsetStr = `UTC${offsetHours >= 0 ? '+' : ''}${offsetHours}`;
  return { name: timeZone, offset: offsetStr };
}
```

This should be inserted between line 66 (closing brace of calculateDateRange) and line 68 (export function KLineChart).


- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "feat: add timezone info helper function"
```

---

## Task 2: Add Timezone State to Component

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:77`

- [ ] **Step 1: Add timezone state**

After the `useToast` hook declaration (line 76), add this new line at line 77:

```typescript
const [timezoneInfo] = useState(getTimezoneInfo());
```

The code should look like:
```typescript
const { toast } = useToast();
const [timezoneInfo] = useState(getTimezoneInfo());

// Reset timeRange when assetType changes
```


- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "feat: add timezone state to KLineChart component"
```

---

## Task 3: Add Custom Time Formatter to Chart Config

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:177-192`

- [ ] **Step 1: Update chart localization config**

Find the chart creation code (line 174) and update the `localization` section (lines 177-180). Replace the existing localization object with:

```typescript
localization: {
  locale: 'en-US',
  dateFormat: 'yyyy-MM-dd',  // Keep existing property
  // Add custom time formatter for tooltips and crosshair
  timeFormatter: (timestamp: number) => {
    // timestamp is Unix seconds, convert to milliseconds
    const date = new Date(timestamp * 1000);
    // Format as local time string
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  },
},
```

Also update the `timeScale` section (lines 189-192) to add `secondsVisible: false` (this prevents showing seconds for minute-level data):

```typescript
timeScale: {
  borderColor: '#334155',
  timeVisible: true,
  secondsVisible: false,  // Add this line
},
```


- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

- [ ] **Step 3: Test in browser**

Run: `cd frontend && npm run dev`
Open: `http://localhost:3000`
Navigate to crypto chart, hover over data points
Expected: Tooltip shows formatted local time (e.g., "03/23/2026, 16:00")

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "feat: add custom time formatter for local timezone display"
```

---

## Task 4: Add Timezone Indicator UI

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:333-343`

- [ ] **Step 1: Update chart header JSX**

Find the chart header section (lines 333-343). The current structure is:

```typescript
<div className="flex items-center justify-between mb-3">
  <h3 className="text-sm font-semibold">
    {selectedStock} - K-Line Chart
  </h3>
  <TimeRangeSelector ... />
</div>
```

Update it to wrap the h3 in a flex container and add the timezone indicator:

```typescript
<div className="flex items-center justify-between mb-3">
  <div className="flex items-center gap-2">
    <h3 className="text-sm font-semibold">
      {selectedStock} - K-Line Chart
    </h3>
    <span className="text-xs text-muted-foreground" title={timezoneInfo.name}>
      ({timezoneInfo.offset})
    </span>
  </div>
  <TimeRangeSelector
    value={timeRange}
    onChange={setTimeRange}
    disabled={loading}
    assetType={assetType}
  />
</div>
```


- [ ] **Step 2: Verify TypeScript compilation**

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

- [ ] **Step 3: Test timezone indicator display**

Run: `cd frontend && npm run dev`
Open: `http://localhost:3000`
Navigate to crypto chart
Expected: Chart header shows "(UTC+X)" next to title, hover shows full timezone name

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "feat: add timezone indicator to chart header"
```

---

## Task 5: Manual Testing & Verification

**Files:**
- Test: `frontend/src/components/chart/KLineChart.tsx`

- [ ] **Step 1: Test intraday data (15M, 1H, 4H)**

Run: `cd frontend && npm run dev`
Open: `http://localhost:3000`
Steps:
1. Select a crypto symbol (e.g., BTC-USDT)
2. Switch to 15M timeframe
3. Hover over data points
4. Check X-axis labels
Expected: Times display in local timezone, tooltip shows formatted local time

- [ ] **Step 2: Test daily+ data (1D, 1W, 1M)**

Steps:
1. Switch to 1D timeframe
2. Hover over data points
3. Check X-axis labels
Expected: Dates display correctly (YYYY-MM-DD format, timezone-agnostic)

- [ ] **Step 3: Verify timezone indicator**

Expected: Header shows correct timezone offset (e.g., "(UTC+8)" for Asia/Shanghai)

- [ ] **Step 4: Cross-browser testing**

Test in: Chrome, Firefox, Safari (if available)
Expected: Consistent timezone display across browsers

- [ ] **Step 5: Document testing results**

Document results in the commit message when committing Task 5 changes, or create a simple note. Example format:
```
Tested on: 2026-03-23
Browser: Chrome 120
System timezone: Asia/Shanghai (UTC+8)
Results: PASS - All timezone displays working correctly
```


---

## Task 6: Final Commit and Cleanup

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx`

- [ ] **Step 1: Review all changes**

Run: `git diff main frontend/src/components/chart/KLineChart.tsx`
Expected: Only timezone-related changes visible

- [ ] **Step 2: Run final build**

Run: `cd frontend && npm run build`
Expected: Clean build with no errors or warnings

- [ ] **Step 3: Create final commit if needed**

If any cleanup was done:
```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "chore: final cleanup for timezone adaptation"
```

- [ ] **Step 4: Verify git log**

Run: `git log --oneline -6`
Expected: See all timezone-related commits

---

## Success Criteria

✅ Chart displays times in user's browser timezone
✅ Timezone indicator shows current timezone offset
✅ Tooltip/crosshair shows formatted local time
✅ X-axis labels show local time for intraday data
✅ Daily+ data continues to work correctly
✅ No TypeScript compilation errors
✅ No backend code changes

---

## Rollback Plan

If issues arise:

```bash
# Revert all changes
git log --oneline -6  # Find commit before timezone changes
git reset --hard <commit-hash>

# Or revert specific commits
git revert <commit-hash>
```

---

## Notes

- Current timestamp conversion logic (lines 211-221) is already correct for timezone handling
- `new Date()` automatically handles timezone conversion from UTC ISO strings
- `lightweight-charts` automatically renders Unix timestamps in local timezone
- No changes needed to backend API or data format
