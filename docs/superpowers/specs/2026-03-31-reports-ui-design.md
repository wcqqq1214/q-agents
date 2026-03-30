# Reports Area UI Design

## Overview

Design for the frontend reports area that displays historical analysis queries with expandable details showing all agent reports (CIO, Quant, News, Social).

## Requirements

- Display list of historical analysis queries with timestamps
- Show CIO summary (derived from first ~200 chars of `reports.cio`) in collapsed state
- Expand to show all reports (CIO, Quant, News, Social) when user clicks "View Full Analysis"
- Use mock data for initial UI testing
- Sort by timestamp (newest first)
- Follow shadcn/ui design patterns and project conventions

## Architecture

### Component Structure

```
ReportsPage (Client Component)
├── Header (Title + Description)
├── EmptyState (when no reports)
└── Accordion (shadcn/ui) — single instance wrapping all items
    └── AccordionItem (per analysis record, direct child of Accordion)
        ├── AccordionTrigger (collapsed card)
        │   ├── Asset symbol + Badge
        │   ├── User query
        │   ├── Timestamp
        │   └── CIO summary (truncated, derived at render time)
        └── AccordionContent (expanded reports)
            └── Tabs (switch between reports)
                ├── Tab: CIO Decision
                ├── Tab: Quant Analysis
                ├── Tab: News Sentiment
                └── Tab: Social Sentiment
```

**Important:** `Accordion` is instantiated once in `page.tsx`. `ReportCard` renders `AccordionItem` (and its children) — it does NOT wrap itself in its own `Accordion`. This ensures correct multi-item open/close behavior per shadcn/ui composition rules.

### Data Structure

```typescript
// Mock-only type — separate from the existing `Report` interface in types.ts
// Will be unified with the real API shape when backend integration is added.
interface AnalysisReport {
  id: string;
  symbol: string;
  assetType: 'stocks' | 'crypto';
  query: string;
  timestamp: string; // ISO 8601 format
  reports: {
    cio: string;   // Full CIO decision (Markdown)
    quant: string; // Quant analysis report (Markdown)
    news: string;  // News sentiment analysis (Markdown)
    social: string; // Social sentiment analysis (Markdown)
  };
}
```

Note: No `cio_summary` field. The collapsed trigger derives its summary by truncating `reports.cio` to ~200 characters at render time, avoiding a redundant field that would need to be kept in sync.

### Mock Data

- 3-5 historical analysis records
- Different assets (AAPL, TSLA, NVDA, BTC, ETH)
- Time span: past week
- Report content in Markdown format (headings, lists, bold, etc.)

## UI Design

### AccordionTrigger (Collapsed State)

**Layout:**
- **Top row:** Asset symbol (large font) + Badge (asset type: stocks/crypto) + Timestamp (right-aligned, muted)
- **Middle row:** User query (normal font, single-line truncate)
- **Bottom row:** CIO summary (muted small text, 2-3 lines truncate with ellipsis, derived from `reports.cio`)
- **Right side:** Expand/collapse icon (Accordion built-in)

### AccordionContent (Expanded State)

**Layout:**
- Use `Tabs` component with 4 tabs:
  - **CIO Decision** (default selected)
  - **Quant Analysis**
  - **News Sentiment**
  - **Social Sentiment**
- Each tab content rendered with `MarkdownRenderer` component
- Tab content area scrollable, max height ~400-500px
- Empty tab content shows fallback message: "No report available."

### Empty State

When `mockReports` array is empty, render a centered message:
> "No analyses yet. Run your first analysis from the main page."

### Loading State

The existing skeleton in `page.tsx` serves as the loading state. No changes needed — the mock data loads synchronously so the skeleton will not be visible in the mock phase.

### Styling Guidelines

- Use shadcn/ui semantic colors (`bg-background`, `text-muted-foreground`, etc.)
- Use `flex flex-col gap-*` instead of `space-y-*` (fix existing `space-y-*` in `page.tsx` during modification)
- Timestamp format: absolute `YYYY-MM-DD HH:mm` using `date-fns format()` for items older than 24h; relative (e.g. "2 hours ago") using `date-fns formatDistanceToNow()` for items within 24h
- Accordion items separated with `gap-4`
- Follow all shadcn/ui composition rules

## Implementation Plan

### Step 0 — Install Accordion component

```bash
cd frontend && pnpm dlx shadcn@latest add accordion
```

This must run before any other step. The `Accordion` component does not exist in `/frontend/src/components/ui/`.

### Files to Create/Modify

1. **`/frontend/src/lib/mock-data/reports.ts`** (new)
   - Define `AnalysisReport` type (mock-only, not exported from `types.ts`)
   - Export `mockReports: AnalysisReport[]` array with 3-5 records

2. **`/frontend/src/components/reports/ReportCard.tsx`** (new)
   - Renders `AccordionItem` + `AccordionTrigger` + `AccordionContent`
   - Receives `report: AnalysisReport` as prop
   - Contains Tabs logic for the 4 report types
   - Derives CIO summary from `reports.cio` at render time

3. **`/frontend/src/app/reports/page.tsx`** (modify)
   - Replace skeleton with real layout
   - Import `mockReports` from mock-data
   - Render single `Accordion` wrapping `ReportCard` components
   - Sort by timestamp descending
   - Replace `space-y-*` with `flex flex-col gap-*`
   - Add empty state

### Required shadcn/ui Components

- `Accordion` — **must be installed (Step 0)**
- `Tabs` — check if installed, add if needed
- `Badge` — check if installed, add if needed
- `MarkdownRenderer` — reuse from `/frontend/src/components/chat/MarkdownRenderer.tsx`

### Security Note

`MarkdownRenderer` uses a regex-based Markdown-to-HTML pipeline with `dangerouslySetInnerHTML`. Report content originates from LLM output. This risk is accepted for the mock/UI phase. When connecting to the real API, add a `DOMPurify` sanitization pass before rendering.

## Technical Constraints

- Must follow Next.js 16+ conventions
- TypeScript strict mode — no explicit `any` types
- Must use `'use client'` directive for components with state/effects
- Follow all shadcn/ui critical rules (see `/frontend/.agents/skills/shadcn/SKILL.md`)

## Success Criteria

- Accordion installs and compiles without errors
- Reports list displays with proper styling and layout
- Accordion expands/collapses smoothly; multiple items can be open simultaneously
- Tabs switch between all 4 report types
- Markdown content renders correctly
- Empty state renders when no reports
- Timestamp shows relative for <24h, absolute for older
- No `space-y-*` in modified files
- No TypeScript errors (`pnpm type-check` passes)
- No ESLint violations (`pnpm lint` passes)
