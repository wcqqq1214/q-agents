# Frontend Settings Display Preferences Only Design

**Problem**

The frontend `settings` page currently mixes two different responsibilities:
- local display preferences owned by the frontend
- backend API key configuration that should stay managed on the backend side

This gives the frontend an unnecessary capability to read and update backend service credentials through `/api/settings`.

**Goal**

Keep `/settings` as the place for frontend display preferences, but remove all frontend API key management UI and the frontend interfaces that call the backend settings API.

**Design**

## Scope

- Keep the `/settings` route and navbar entry.
- Keep the display preference control for price color convention.
- Remove API key configuration UI from the settings page.
- Remove frontend `getSettings` and `updateSettings` helpers.
- Remove frontend `SettingsRequest` and `SettingsResponse` types.
- Do not remove the backend `/api/settings` route in this change.

## Behavior

1. Visiting `/settings` must show only display-preference content.
2. The page must no longer fetch backend settings on mount.
3. The page must no longer expose a save action for backend configuration.
4. The trend color preference must keep its existing local toggle behavior.

## Persistence

- The price color convention remains a frontend-local preference.
- The existing persistence mechanism is `localStorage` via `TrendColorProvider`.
- This change must not alter the current key, initialization path, or document-class toggling used by the trend color preference.

## Component and Interface Changes

- Simplify `frontend/src/app/settings/page.tsx` so it only renders the display-preferences card and related copy.
- Delete settings API methods from `frontend/src/lib/api.ts`.
- Delete settings request/response types from `frontend/src/lib/types.ts`.
- Run a frontend-wide reference check for `getSettings`, `updateSettings`, `SettingsRequest`, and `SettingsResponse` before removing them so no hidden consumer is missed.

## Files

- Modify `frontend/src/app/settings/page.tsx`
- Modify `frontend/src/lib/api.ts`
- Modify `frontend/src/lib/types.ts`
- Add a frontend regression test covering the removed API-key-management capability

## Risks

- The `/settings` page copy currently implies configuration changes are saved immediately. That language must be updated so it does not refer to removed backend settings behavior.
- Removing frontend types and helpers must not affect unrelated API consumers in `frontend/src/lib/api.ts`.
- The backend `/api/settings` route will remain temporarily without a frontend caller after this change. Its long-term ownership and replacement path should be handled separately from this frontend cleanup.

## Test Strategy

- Add a red-green regression test using the existing `node:test` source-assertion pattern.
- Verify the settings page still contains display-preference UI and no longer contains API key labels or save-config copy.
- Verify the page source no longer calls `api.getSettings()` or `api.updateSettings()`.
- Verify the frontend API client and shared types no longer export settings-specific interfaces.
- Run `pnpm type-check` so any leftover TypeScript references to removed settings types or helpers fail fast.
