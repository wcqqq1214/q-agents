# Reports Real API Design

## Summary

Replace the frontend reports page's mock data with real report data from the backend while keeping the existing accordion-based interaction. Preserve the visible `assetType` badge by adding a real `asset_type` field to the backend report contract, and remove the unused `/reports/[id]` placeholder page.

## Goals

- Show real generated reports on `/reports` instead of `mockReports`.
- Keep the current list-with-inline-expansion UX.
- Keep showing the `assetType` badge on each report card.
- Load reports once when entering `/reports`.
- Provide a manual refresh button.
- Delete the unused report detail placeholder route.
- Create and implement the work on an isolated git branch.

## Non-Goals

- No detail-page navigation or deep-link report viewer.
- No polling, auto-refresh, or SSE-based live updates on `/reports`.
- No new frontend testing framework.
- No redesign of the reports page layout.
- No large refactor of unrelated API or reporting code.

## Current State

### Frontend

- [frontend/src/app/reports/page.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/app/reports/page.tsx) renders `mockReports` from [frontend/src/lib/mock-data/reports.ts](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/lib/mock-data/reports.ts).
- [frontend/src/components/reports/ReportCard.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/components/reports/ReportCard.tsx) depends on the mock-only `AnalysisReport` type and reads `report.assetType`.
- [frontend/src/lib/api.ts](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/lib/api.ts) already has `getReports()` and `getReport()`, but the reports page does not use them.
- [frontend/src/app/reports/[id]/page.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/app/reports/[id]/page.tsx) exists as an unused placeholder route.

### Backend

- [app/api/routes/reports.py](/home/wcqqq21/q-agents/.worktrees/reports-real-api/app/api/routes/reports.py) exposes `GET /api/reports` and `GET /api/reports/{report_id}`.
- [app/graph_multi.py](/home/wcqqq21/q-agents/.worktrees/reports-real-api/app/graph_multi.py) writes `report.json` through `_build_aggregated_report()`.
- The current report API contract does not include `asset_type`.
- The backend already contains asset extraction heuristics for report generation, including common crypto tickers and pair formats.

## Proposed Approach

Use the existing backend reports API as the frontend data source, and extend the backend report contract with a real `asset_type` field. The frontend will consume the real `Report` type directly instead of mapping from a mock-only shape.

This keeps the implementation small, preserves the current UI, avoids frontend-only guessing, and ensures the `assetType` badge remains backed by a real field.

## Architecture

### Unit 1: Backend aggregated report contract

Responsibility:
- Make `report.json` contain a stable `asset_type` field.

Files:
- Modify [app/graph_multi.py](/home/wcqqq21/q-agents/.worktrees/reports-real-api/app/graph_multi.py)

Behavior:
- Add `asset_type` to the object returned by `_build_aggregated_report()`.
- Derive `asset_type` from the same asset-identification logic already used for report generation.
- Allowed values are exactly `"stocks"` or `"crypto"`.

### Unit 2: Backend API schema and compatibility fallback

Responsibility:
- Return `asset_type` from report APIs for both newly generated and historical reports.

Files:
- Modify [app/api/models/schemas.py](/home/wcqqq21/q-agents/.worktrees/reports-real-api/app/api/models/schemas.py)
- Modify [app/api/routes/reports.py](/home/wcqqq21/q-agents/.worktrees/reports-real-api/app/api/routes/reports.py)

Behavior:
- Extend the FastAPI `Report` schema with `asset_type`.
- When reading `report.json`, prefer the stored `asset_type`.
- If an older `report.json` lacks `asset_type`, infer it server-side using the same classification rule and include it in the response.
- Do not mutate historical report files as part of API reads.

### Unit 3: Frontend reports page data loading

Responsibility:
- Replace mock data with real API data on `/reports`.

Files:
- Modify [frontend/src/app/reports/page.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/app/reports/page.tsx)
- Modify [frontend/src/lib/types.ts](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/lib/types.ts)

Behavior:
- Add `asset_type` to the frontend `Report` type.
- On first render of `/reports`, request `api.getReports()`.
- Sort results by descending `timestamp`.
- Store the result in component state.
- Add a refresh button that re-runs the same request and replaces the current list.

### Unit 4: Frontend report card contract cleanup

Responsibility:
- Render the same report UI from the real API shape.

Files:
- Modify [frontend/src/components/reports/ReportCard.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/components/reports/ReportCard.tsx)

Behavior:
- Switch the prop type from the mock-only `AnalysisReport` to the real `Report`.
- Read the badge from `report.asset_type`.
- Continue rendering markdown tabs from `report.reports`.
- Keep the current accordion content structure.

### Unit 5: Dead code removal

Responsibility:
- Remove unused reports scaffolding that no longer matches the product flow.

Files:
- Delete [frontend/src/app/reports/[id]/page.tsx](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/app/reports/[id]/page.tsx)
- Delete [frontend/src/lib/mock-data/reports.ts](/home/wcqqq21/q-agents/.worktrees/reports-real-api/frontend/src/lib/mock-data/reports.ts) if no references remain

Behavior:
- The reports feature should only exist through `/reports` with inline expansion.
- No stale placeholder route or dead mock data should remain after the change.

## Data Contract

### Backend `report.json`

Add:

```json
{
  "asset_type": "stocks"
}
```

Rules:
- `"stocks"` for equities and non-crypto assets handled by the current report flow
- `"crypto"` for supported crypto tickers or pair formats recognized by backend classification

### API response shape

`GET /api/reports` and `GET /api/reports/{report_id}` must include:

```json
{
  "id": "20260403_120000_NVDA",
  "symbol": "NVDA",
  "asset_type": "stocks",
  "timestamp": "2026-04-03T04:00:00Z",
  "query": "Analyze NVDA",
  "reports": {
    "cio": "...",
    "quant": "...",
    "news": "...",
    "social": "..."
  }
}
```

The API must tolerate old `report.json` files without `asset_type`.

## Classification Rules

Use one backend-owned classification helper that returns `"stocks"` or `"crypto"`.

Requirements:
- Reuse the existing crypto-aware heuristics already present in the reporting flow.
- Treat common crypto tickers such as `BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `ADA`, `DOGE`, `AVAX`, `DOT`, and `LINK` as `crypto`.
- Treat explicit crypto pair formats such as `BTC-USD` as `crypto`.
- Default to `stocks` when the value does not match the crypto rules.

The exact helper name can be chosen during implementation, but the rule must live on the backend and be used in both report writing and report reading.

## User Experience

### Reports page

- Keep the current title and accordion layout.
- Show a refresh button near the page header.
- Disable the button while a request is in flight.
- Preserve the existing empty-state copy for "no reports yet".

### Loading behavior

- When the page first loads, show a lightweight loading state rather than immediately rendering the empty-state copy.
- When refresh is clicked, keep the page shell visible and refresh the list contents once the request resolves.

### Failure behavior

- If the request fails, log the error with `console.error`.
- Do not show a toast, inline banner, or modal.
- Treat the page as having no reports and render the empty state.

## Error Handling

### Backend

- Invalid or unreadable report directories should continue to be skipped rather than failing the whole list endpoint.
- Missing `asset_type` on older reports is not an error; it should be backfilled in the API response.

### Frontend

- Network and parsing failures should not crash the page.
- Failed requests should leave the user on the reports page with the normal empty state.

## Testing Strategy

Follow TDD during implementation.

### Backend tests

Add or extend pytest coverage for:

- aggregated `report.json` includes `asset_type`
- new reports API responses include stored `asset_type`
- historical reports without `asset_type` still return inferred `asset_type`
- representative stock and crypto cases classify correctly

Prefer focused tests near existing reporting and API route tests.

### Frontend verification

Do not add a new frontend test framework in this task.

Verify with existing project checks:

- `pnpm lint`
- `pnpm type-check`
- optionally `pnpm build` if needed to catch route-level or RSC/client-boundary issues

## Implementation Constraints

- Keep the existing accordion interaction; no detail-page navigation.
- Do not introduce frontend guessing for `asset_type`.
- Do not expand the feature into auto-refresh or polling.
- Do not refactor unrelated report rendering behavior.
- Use the isolated branch created for this task.

## Risks and Mitigations

### Risk: Historical reports missing `asset_type`

Mitigation:
- Infer server-side during API reads so the frontend contract stays stable.

### Risk: Frontend assumes mock-only fields

Mitigation:
- Remove the mock-only `AnalysisReport` dependency and use the real API type directly.

### Risk: Loading and empty states become ambiguous

Mitigation:
- Keep a distinct initial loading state before rendering the standard empty-state message.

## Acceptance Criteria

- `/reports` no longer imports or renders `mockReports`.
- `/reports` loads real reports from `GET /api/reports` on page entry.
- `/reports` includes a working refresh button.
- The report card badge still shows `stocks` or `crypto`.
- `asset_type` is provided by the backend, not guessed in the frontend.
- Historical reports without `asset_type` still display a correct badge via API fallback.
- `/reports/[id]` placeholder route is removed.
- Unused mock report data is removed.
- Backend pytest coverage exists for the new contract behavior.
- Frontend passes lint and type-check after the integration.
