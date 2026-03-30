# Reports Area UI Design

## Overview

Design for the frontend reports area that displays historical analysis queries with expandable details showing all agent reports (CIO, Quant, News, Social).

## Requirements

- Display list of historical analysis queries with timestamps
- Show CIO summary in collapsed state
- Expand to show all reports (CIO, Quant, News, Social) when user clicks "View Full Analysis"
- Use mock data for initial UI testing
- Sort by timestamp (newest first)
- Follow shadcn/ui design patterns and project conventions

## Architecture

### Component Structure

```
ReportsPage (Client Component)
├── Header (Title + Description)
├── Accordion (shadcn/ui)
    └── AccordionItem (per analysis record)
        ├── AccordionTrigger (collapsed card)
        │   ├── Asset symbol + Badge
        │   ├── User query
        │   ├── Timestamp
        │   └── CIO summary (truncated)
        └── AccordionContent (expanded reports)
            └── Tabs (switch between reports)
                ├── Tab: CIO Decision
                ├── Tab: Quant Analysis
                ├── Tab: News Sentiment
                └── Tab: Social Sentiment
```

### Data Structure

```typescript
interface AnalysisReport {
  id: string;
  symbol: string;
  query: string;
  timestamp: string; // ISO 8601 format
  cio_summary: string; // CIO summary for list display
  reports: {
    cio: string; // Full CIO decision (Markdown)
    quant: string; // Quant analysis report (Markdown)
    news: string; // News sentiment analysis (Markdown)
    social: string; // Social sentiment analysis (Markdown)
  };
}
```

### Mock Data

- 3-5 historical analysis records
- Different assets (AAPL, TSLA, NVDA, etc.)
- Time span: past week
- Report content in Markdown format (headings, lists, bold, etc.)

## UI Design

### AccordionTrigger (Collapsed State)

**Layout:**
- **Top row:** Asset symbol (large font) + Badge (asset type: stocks/crypto) + Timestamp (right-aligned, muted)
- **Middle row:** User query (normal font, single-line truncate)
- **Bottom row:** CIO summary (muted small text, 2-3 lines truncate with ellipsis)
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

### Styling Guidelines

- Use shadcn/ui semantic colors (`bg-background`, `text-muted-foreground`, etc.)
- Use `gap-*` instead of `space-y-*`
- Timestamp format: relative time ("2 hours ago") or absolute ("2026-03-31 10:30")
- Accordion items separated with `gap-4`
- Follow all shadcn/ui composition rules (no `space-y-*`, use `size-*` for equal dimensions, etc.)

## Implementation Plan

### Files to Create/Modify

1. **`/frontend/src/lib/mock-data/reports.ts`** (new)
   - Store mock data
   - Export `mockReports` array

2. **`/frontend/src/components/reports/ReportCard.tsx`** (new)
   - Single report card component
   - Receives `AnalysisReport` as props
   - Contains Accordion + Tabs logic

3. **`/frontend/src/app/reports/page.tsx`** (modify)
   - Import mock data
   - Use Accordion to wrap multiple ReportCards
   - Sort by timestamp descending

4. **`/frontend/src/lib/types.ts`** (modify)
   - Add `AnalysisReport` type definition

### Required shadcn/ui Components

- `Accordion` (check if installed, add if needed)
- Existing components: `Card`, `Badge`, `Tabs`, `MarkdownRenderer`

### Time Formatting

- Use `date-fns` library (if available in project) or native `Intl.DateTimeFormat`
- Display format: `2026-03-31 10:30` or relative time

### Markdown Rendering

- Reuse existing `MarkdownRenderer` component (`/frontend/src/components/chat/MarkdownRenderer.tsx`)

## Technical Constraints

- Must follow Next.js 16+ conventions (breaking changes from older versions)
- TypeScript strict mode enabled
- No explicit `any` types allowed
- Must use `'use client'` directive for components with state/effects
- Follow all shadcn/ui critical rules (see `/frontend/.agents/skills/shadcn/SKILL.md`)

## Success Criteria

- Reports list displays with proper styling and layout
- Accordion expands/collapses smoothly
- Tabs switch between different reports
- Markdown content renders correctly
- Mock data displays properly
- Responsive design works on different screen sizes
- No TypeScript errors
- No ESLint violations
