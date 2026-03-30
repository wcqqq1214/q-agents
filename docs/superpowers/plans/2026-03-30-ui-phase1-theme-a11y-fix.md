# Phase 1 UI Fix: Theme & A11y Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up hardcoded colors and fix ARIA labels to establish a consistent theme system and improve accessibility.

**Architecture:** Extend CSS variable system with chart-specific colors (`--chart-up`/`--chart-down`), replace all hardcoded hex colors with CSS variables, add theme switching support to Canvas-based chart, and fix missing/incorrect ARIA labels.

**Tech Stack:** Tailwind CSS v4, Next.js 16, next-themes, lightweight-charts, TypeScript strict mode

---

## File Structure

### Files to Modify

1. **`frontend/src/app/globals.css`**
   - Add `--chart-up` and `--chart-down` variables to `:root` and `.dark`
   - Register variables in `@theme inline` block

2. **`frontend/src/components/stock/StockCard.tsx`**
   - Replace `text-green-500`/`text-red-500` with `text-chart-up`/`text-chart-down`

3. **`frontend/src/components/chart/KLineChart.tsx`**
   - Import `useTheme` from `next-themes`
   - Replace all hardcoded hex colors with CSS variables
   - Add `resolvedTheme` to useEffect dependencies for theme switching

4. **`frontend/src/components/layout/ThemeToggle.tsx`**
   - Replace Chinese `aria-label` with English

5. **`frontend/src/components/chat/ChatPanel.tsx`**
   - Add `aria-label` to submit button

6. **`frontend/src/components/asset/AssetSelector.tsx`**
   - Add `aria-label` to refresh button
   - Fix template string className to use `cn()`

---

## Task 1: Define CSS Variables for Chart Colors

**Files:**
- Modify: `frontend/src/app/globals.css:50-83` (`:root` block)
- Modify: `frontend/src/app/globals.css:85-117` (`.dark` block)
- Modify: `frontend/src/app/globals.css:7-48` (`@theme inline` block)

- [ ] **Step 1: Add chart color variables to `:root` block**

Open `frontend/src/app/globals.css` and locate the `:root` block (around line 50). Add the following lines after the existing variables (before the closing `}`):

```css
  --chart-up: 142.1 76.2% 36.3%;      /* green-500 */
  --chart-down: 0 84.2% 60.2%;        /* red-500 */
```

- [ ] **Step 2: Add chart color variables to `.dark` block**

Locate the `.dark` block (around line 85). Add the following lines after the existing variables (before the closing `}`):

```css
  --chart-up: 142.1 70.6% 45.3%;      /* green-400 */
  --chart-down: 0 72.2% 50.6%;        /* red-400 */
```

- [ ] **Step 3: Register variables in `@theme inline` block**

Locate the `@theme inline` block (around line 7). Add the following lines after the existing color registrations (before the closing `}`):

```css
  --color-chart-up: hsl(var(--chart-up));
  --color-chart-down: hsl(var(--chart-down));
```

- [ ] **Step 4: Verify Tailwind compilation**

Run the dev server to ensure Tailwind compiles the new variables:

```bash
cd frontend && pnpm dev
```

Expected: No compilation errors, server starts successfully

- [ ] **Step 5: Commit CSS variable definitions**

```bash
git add frontend/src/app/globals.css
git commit -m "feat(theme): add chart-up and chart-down CSS variables for consistent color system"
```

---

## Task 2: Update StockCard.tsx Color Classes

**Files:**
- Modify: `frontend/src/components/stock/StockCard.tsx:17`

- [ ] **Step 1: Replace hardcoded color classes**

Open `frontend/src/components/stock/StockCard.tsx` and locate line 17. Replace:

```typescript
const changeColor = stock.change === undefined
  ? 'text-muted-foreground'
  : isPositive ? 'text-green-500' : 'text-red-500';
```

With:

```typescript
const changeColor = stock.change === undefined
  ? 'text-muted-foreground'
  : isPositive ? 'text-chart-up' : 'text-chart-down';
```

- [ ] **Step 2: Verify TypeScript compilation**

Run type check to ensure no type errors:

```bash
cd frontend && pnpm type-check
```

Expected: No type errors

- [ ] **Step 3: Test in browser**

Start dev server and verify stock cards display with correct colors:

```bash
cd frontend && pnpm dev
```

Open http://localhost:3000 and check:
- Stock cards with positive change show green color
- Stock cards with negative change show red color
- Colors match the chart colors visually

- [ ] **Step 4: Test theme switching**

In the browser:
1. Click the theme toggle button
2. Verify stock card colors update correctly in both light and dark modes

Expected: Colors change from green-500/red-500 (light) to green-400/red-400 (dark)

- [ ] **Step 5: Commit StockCard changes**

```bash
git add frontend/src/components/stock/StockCard.tsx
git commit -m "fix(stock-card): use semantic chart color variables instead of hardcoded green/red"
```

---

## Task 3: Update KLineChart.tsx - Import Theme Hook

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:1-10` (imports)
- Modify: `frontend/src/components/chart/KLineChart.tsx:87-98` (component start)

- [ ] **Step 1: Add useTheme import**

Open `frontend/src/components/chart/KLineChart.tsx` and add the import at the top (after existing imports):

```typescript
import { useTheme } from 'next-themes';
```

- [ ] **Step 2: Add resolvedTheme to component**

Locate the component function (around line 87) and add `useTheme` hook after the existing hooks:

```typescript
export function KLineChart({ selectedStock, assetType }: KLineChartProps) {
  const defaultTimeRange: TimeRange = assetType === 'crypto' ? '15M' : 'D';
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);
  const [ohlcData, setOhlcData] = useState<OHLCRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const [timezoneInfo] = useState(getTimezoneInfo());
  const { resolvedTheme } = useTheme();  // Add this line
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors

- [ ] **Step 4: Commit theme hook addition**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "feat(chart): add useTheme hook for theme switching support"
```

---

## Task 4: Update KLineChart.tsx - Replace Layout Colors

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:195-256` (chart creation)

- [ ] **Step 1: Replace textColor**

Locate the chart creation code (around line 195) and find the `layout` configuration (around line 220). Replace:

```typescript
layout: {
  background: { color: 'transparent' },
  textColor: '#d1d5db',
},
```

With:

```typescript
layout: {
  background: { color: 'transparent' },
  textColor: 'hsl(var(--muted-foreground))',
},
```

- [ ] **Step 2: Replace grid colors**

In the same chart configuration, find the `grid` section (around line 224). Replace:

```typescript
grid: {
  vertLines: { color: '#334155' },
  horzLines: { color: '#334155' },
},
```

With:

```typescript
grid: {
  vertLines: { color: 'hsl(var(--border))' },
  horzLines: { color: 'hsl(var(--border))' },
},
```

- [ ] **Step 3: Replace timeScale borderColor**

Find the `timeScale` section (around line 228). Replace:

```typescript
timeScale: {
  borderColor: '#334155',
  // ... other properties
},
```

With:

```typescript
timeScale: {
  borderColor: 'hsl(var(--border))',
  // ... other properties
},
```

- [ ] **Step 4: Replace rightPriceScale borderColor**

Find the `rightPriceScale` section (around line 253). Replace:

```typescript
rightPriceScale: {
  borderColor: '#334155',
},
```

With:

```typescript
rightPriceScale: {
  borderColor: 'hsl(var(--border))',
},
```

- [ ] **Step 5: Verify and commit layout color changes**

```bash
cd frontend && pnpm type-check
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "fix(chart): replace hardcoded layout colors with CSS variables"
```

---

## Task 5: Update KLineChart.tsx - Replace Candlestick Colors

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:259-265` (candlestick series)

- [ ] **Step 1: Replace candlestick colors**

Locate the candlestick series creation (around line 259). Replace:

```typescript
const series = chart.addSeries(CandlestickSeries, {
  upColor: '#22c55e',
  downColor: '#ef4444',
  wickUpColor: '#22c55e',
  wickDownColor: '#ef4444',
  priceScaleId: 'right',
});
```

With:

```typescript
const series = chart.addSeries(CandlestickSeries, {
  upColor: 'hsl(var(--chart-up))',
  downColor: 'hsl(var(--chart-down))',
  wickUpColor: 'hsl(var(--chart-up))',
  wickDownColor: 'hsl(var(--chart-down))',
  priceScaleId: 'right',
});
```

- [ ] **Step 2: Verify and commit candlestick color changes**

```bash
cd frontend && pnpm type-check
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "fix(chart): replace hardcoded candlestick colors with chart color variables"
```

---

## Task 6: Update KLineChart.tsx - Replace Volume Colors

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:310-315` (volume data)

- [ ] **Step 1: Replace volume bar colors**

Locate the volume data creation loop (around line 310). Replace:

```typescript
volumeData.push({
  time,
  value: d.volume,
  color: d.close >= d.open ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)',
});
```

With:

```typescript
volumeData.push({
  time,
  value: d.volume,
  color: d.close >= d.open ? 'hsl(var(--chart-up) / 0.6)' : 'hsl(var(--chart-down) / 0.6)',
});
```

- [ ] **Step 2: Verify and commit volume color changes**

```bash
cd frontend && pnpm type-check
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "fix(chart): replace hardcoded volume colors with chart color variables"
```

---

## Task 7: Update KLineChart.tsx - Replace Legend Colors and Add Theme Dependency

**Files:**
- Modify: `frontend/src/components/chart/KLineChart.tsx:341` (legend color)
- Modify: `frontend/src/components/chart/KLineChart.tsx:425` (useEffect dependencies)

- [ ] **Step 1: Replace legend color**

Locate the crosshair move handler (around line 341). Replace:

```typescript
const color = isUp ? '#22c55e' : '#ef4444';
```

With:

```typescript
const color = isUp ? 'hsl(var(--chart-up))' : 'hsl(var(--chart-down))';
```

- [ ] **Step 2: Add resolvedTheme to useEffect dependencies**

Locate the useEffect that creates the chart (around line 183). Find the dependency array at the end (around line 425). Replace:

```typescript
}, [ohlcData]);
```

With:

```typescript
}, [ohlcData, resolvedTheme]);
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors

- [ ] **Step 4: Test theme switching in browser**

Start dev server:

```bash
cd frontend && pnpm dev
```

Open http://localhost:3000, select a stock, and:
1. Verify chart displays with correct colors
2. Click theme toggle button
3. Verify chart immediately redraws with new colors (green-500/red-500 in light, green-400/red-400 in dark)

Expected: Chart redraws within ~100ms, no flickering

- [ ] **Step 5: Commit legend color and theme switching**

```bash
git add frontend/src/components/chart/KLineChart.tsx
git commit -m "fix(chart): replace legend colors and add theme switching support"
```

---

## Task 8: Fix ThemeToggle.tsx ARIA Labels

**Files:**
- Modify: `frontend/src/components/layout/ThemeToggle.tsx:23` (unmounted state)
- Modify: `frontend/src/components/layout/ThemeToggle.tsx:36` (mounted state)

- [ ] **Step 1: Replace unmounted aria-label**

Open `frontend/src/components/layout/ThemeToggle.tsx` and locate line 23. Replace:

```typescript
aria-label="切换主题"
```

With:

```typescript
aria-label="Toggle theme"
```

- [ ] **Step 2: Replace mounted aria-label**

Locate line 36. Replace:

```typescript
aria-label={isDark ? '切换到浅色模式' : '切换到暗黑模式'}
```

With:

```typescript
aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors

- [ ] **Step 4: Test with keyboard navigation**

In browser:
1. Press Tab key to navigate to theme toggle button
2. Verify button receives focus ring
3. Press Enter to toggle theme
4. Verify theme switches correctly

- [ ] **Step 5: Commit ThemeToggle ARIA fix**

```bash
git add frontend/src/components/layout/ThemeToggle.tsx
git commit -m "fix(a11y): replace Chinese aria-labels with English in ThemeToggle"
```

---

## Task 9: Fix ChatPanel.tsx ARIA Label

**Files:**
- Modify: `frontend/src/components/chat/ChatPanel.tsx:111-117` (submit button)

- [ ] **Step 1: Add aria-label to submit button**

Open `frontend/src/components/chat/ChatPanel.tsx` and locate the submit button (around line 111). Add `aria-label` prop:

```typescript
<Button
  type="submit"
  size="icon"
  disabled={!selectedStock || !query.trim() || isAnalyzing}
  aria-label="Send analysis query"
>
  <Send className="h-4 w-4" />
</Button>
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors

- [ ] **Step 3: Test with keyboard navigation**

In browser:
1. Navigate to chat panel
2. Type a query in the input field
3. Press Tab to focus the submit button
4. Verify button receives focus ring
5. Press Enter to submit

- [ ] **Step 4: Commit ChatPanel ARIA fix**

```bash
git add frontend/src/components/chat/ChatPanel.tsx
git commit -m "fix(a11y): add aria-label to chat submit button"
```

---

## Task 10: Fix AssetSelector.tsx ARIA Label and ClassName

**Files:**
- Modify: `frontend/src/components/asset/AssetSelector.tsx:1-11` (imports)
- Modify: `frontend/src/components/asset/AssetSelector.tsx:113-121` (refresh button)

- [ ] **Step 1: Add cn() import**

Open `frontend/src/components/asset/AssetSelector.tsx` and check the imports at the top. The file currently does NOT import `cn`. Add it after the existing imports (around line 10):

```typescript
import { cn } from '@/lib/utils';
```

The imports section should look like:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { StockCard } from '../stock/StockCard';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';  // Add this line
import type { StockInfo, CryptoQuote } from '@/lib/types';
```

- [ ] **Step 2: Add aria-label and fix className**

Locate the refresh button (around line 113). Replace:

```typescript
<Button
  variant="ghost"
  size="icon"
  className="h-6 w-6"
  onClick={() => fetchQuotes(true)}
  disabled={refreshing}
>
  <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
</Button>
```

With:

```typescript
<Button
  variant="ghost"
  size="icon"
  className="h-6 w-6"
  onClick={() => fetchQuotes(true)}
  disabled={refreshing}
  aria-label="Refresh quotes"
>
  <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
</Button>
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors (cn should now be recognized)

- [ ] **Step 4: Test with keyboard navigation**

In browser:
1. Press Tab to navigate to refresh button
2. Verify button receives focus ring
3. Press Enter to trigger refresh
4. Verify quotes refresh and spinner animates

- [ ] **Step 5: Commit AssetSelector ARIA fix**

```bash
git add frontend/src/components/asset/AssetSelector.tsx
git commit -m "fix(a11y): add aria-label to refresh button and use cn() for className"
```

---

## Task 11: Final Verification and Testing

**Files:**
- Test: All modified files

- [ ] **Step 1: Run full type check**

```bash
cd frontend && pnpm type-check
```

Expected: No type errors across all files

- [ ] **Step 2: Run ESLint**

```bash
cd frontend && pnpm lint
```

Expected: No linting errors

- [ ] **Step 3: Search for remaining hardcoded colors**

```bash
cd frontend/src && grep -r "#[0-9a-fA-F]\{6\}" --include="*.tsx" --include="*.ts" | grep -v node_modules
```

Expected: No results (or only results in non-component files like config)

- [ ] **Step 4: Search for text-green-500 and text-red-500**

```bash
cd frontend/src && grep -r "text-green-500\|text-red-500" --include="*.tsx" --include="*.ts"
```

Expected: No results

- [ ] **Step 5: Manual theme switching test**

In browser at http://localhost:3000:
1. Select a stock (e.g., AAPL)
2. Verify K-line chart displays with correct colors
3. Verify stock cards show correct colors
4. Click theme toggle button
5. Verify all colors update immediately:
   - Chart candlesticks
   - Chart volume bars
   - Chart legend
   - Stock card change percentages
6. Toggle theme multiple times to ensure consistency

- [ ] **Step 6: Manual accessibility test**

Using keyboard only:
1. Press Tab repeatedly to navigate through all interactive elements
2. Verify all buttons receive visible focus rings
3. Verify theme toggle, chat submit, and refresh buttons can be activated with Enter/Space
4. (Optional) Use screen reader to verify aria-labels are announced correctly

- [ ] **Step 7: Create final commit if needed**

If any final adjustments were made during testing:

```bash
git add -A
git commit -m "test: verify Phase 1 UI fixes complete"
```

---

## Completion Checklist

- [ ] All 11 tasks completed
- [ ] All commits follow conventional commit format
- [ ] No TypeScript errors
- [ ] No ESLint errors
- [ ] No hardcoded hex colors remain in component files
- [ ] No `text-green-500` or `text-red-500` classes remain
- [ ] Theme switching works correctly for all components
- [ ] All icon-only buttons have aria-labels
- [ ] Keyboard navigation works for all interactive elements

---

## Notes for Implementation

**DRY Principle:**
- CSS variables defined once in `globals.css`, used everywhere
- No duplication of color values across components

**YAGNI Principle:**
- Only added variables needed for current use case (`--chart-up`/`--chart-down`)
- Did not add unused color variations or additional theme customization

**TDD Approach:**
- Each task includes verification steps before committing
- Manual testing ensures changes work as expected
- Type checking and linting catch errors early

**Frequent Commits:**
- Each logical change gets its own commit
- Commit messages follow conventional commit format
- Easy to review and rollback if needed

---

## ⚠️ Critical Implementation Notes

### Watch Out #1: cn() Import in AssetSelector.tsx (Task 10)

**Risk**: Task 10 uses `cn()` function but may not have the import statement.

**Before modifying className in Task 10, Step 1:**

Check if `cn` is already imported at the top of `frontend/src/components/asset/AssetSelector.tsx`. If not, add:

```typescript
import { cn } from '@/lib/utils';
```

The import should be added with other utility imports, typically after React imports and before component imports.

---

### Watch Out #2: Canvas Memory Leak Prevention (Task 7)

**Risk**: Adding `resolvedTheme` to useEffect dependencies will cause the effect to re-run on theme changes. If the cleanup function is missing or incomplete, multiple chart instances will be created, causing memory leaks and visual overlaps.

**In Task 7, Step 2 (after adding resolvedTheme dependency):**

Verify the useEffect has proper cleanup. The existing useEffect should already have a return statement like:

```typescript
return () => {
  window.removeEventListener('resize', handleResize);
  if (chartRef.current) {
    chartRef.current.remove();
    chartRef.current = null;
  }
};
```

If this cleanup is missing, the chart will leak memory. The current code (as of the spec) already has this cleanup at line 418-424, so this should be fine. But verify it's still there after your changes.

---

### Watch Out #3: Line Number Brittleness

**Note**: Line numbers in this plan are approximate and may shift as you make changes.

**Best Practice**: Use the code snippets provided in each step to locate the target code via pattern matching, not just line numbers. The line numbers are hints, not absolute references.

If you can't find code at the specified line number:
1. Search for the code pattern in the file
2. Use your editor's "Find" feature with the code snippet
3. Look for surrounding context (function names, comments)

---
