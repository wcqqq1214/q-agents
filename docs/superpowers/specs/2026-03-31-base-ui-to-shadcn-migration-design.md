# Design: base-ui → shadcn/ui Migration

**Date:** 2026-03-31  
**Branch:** `feat/shadcn-migration`  
**Style:** new-york  
**Base color:** Zinc

---

## 1. Scope & Goals

Replace all 10 `components/ui/` files that currently depend on `@base-ui/react` and `@radix-ui/react-*` with standard shadcn/ui components. Remove the old dependencies entirely. Update `components.json` to `new-york` style.

**Components to regenerate via `npx shadcn@latest add`:**
- `button` — currently wraps `@base-ui/react` Button
- `input` — currently wraps `@base-ui/react` Input
- `tabs` — currently wraps `@base-ui/react` Tabs (Root, List, Tab, Panel)
- `accordion` — currently wraps `@base-ui/react` Accordion (Root, Item, Header, Trigger, Panel)
- `badge` — currently uses `mergeProps` + `useRender` from base-ui (internal utilities, no shadcn equivalent — straight rewrite to CVA span)
- `label` — currently wraps `@radix-ui/react-label`
- `toast` — currently wraps `@radix-ui/react-toast`
- `toaster` — consumer of toast
- `card` — currently plain HTML/CSS (regenerate for consistency)
- `skeleton` — currently plain HTML/CSS (regenerate for consistency)

**Dependencies to remove:**
- `@base-ui/react`
- `@radix-ui/react-label`
- `@radix-ui/react-toast`

**Dependencies managed by shadcn after migration:**
- `@radix-ui/react-tabs`
- `@radix-ui/react-accordion`
- `@radix-ui/react-label`
- `@radix-ui/react-toast`
- `class-variance-authority` (already present)
- `clsx` + `tailwind-merge` (already present)

---

## 2. Migration Steps

### Step 1 — Create branch
```bash
git checkout -b feat/shadcn-migration
```

### Step 2 — Update components.json
Change `"style": "base-nova"` → `"style": "new-york"` and `"baseColor": "neutral"` → `"baseColor": "zinc"`.

### Step 3 — Ensure lib/utils.ts has cn
`lib/utils.ts` must export:
```ts
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```
This is the single utility function for all shadcn components. Remove any `mergeProps`/`useRender` usage from `badge.tsx` during regeneration.

### Step 4 — Delete old components
Remove all 10 files from `frontend/src/components/ui/`.

### Step 5 — Uninstall old dependencies
```bash
pnpm remove @base-ui/react @radix-ui/react-label @radix-ui/react-toast
```

### Step 6 — Run shadcn init
```bash
npx shadcn@latest init
```
Select: style = new-york, base color = zinc, CSS variables = yes.

**Tailwind v4 note:** This project uses Tailwind v4 (`tailwindcss: "^4"`), which uses CSS-first configuration — there is no `tailwind.config.ts`. If shadcn CLI attempts to write keyframes to `tailwind.config.ts`, ignore that output. Instead, manually add all `@keyframes` and animation utilities to `globals.css` using the `@theme` directive per Tailwind v4 conventions. The CSS variables (Zinc palette, `--radius`) injected by shadcn init into `globals.css` are correct and should be merged carefully with any existing custom variables — do not overwrite the entire file.

### Step 7 — Regenerate all components
```bash
npx shadcn@latest add button input tabs accordion badge label toast toaster card skeleton
```
This installs correct Radix peer deps and generates typed, CVA-based components under `components/ui/`.

### Step 8 — Mount Toaster globally
Add `<Toaster />` to the application root. Check `components/layout/` and `src/app/layout.tsx` — mount it at the top level so toast notifications render app-wide. If the old base-ui setup had no global mount point, this step is required for toast to work at all.

### Step 9 — Fix consumers
Scan and update all files in:
- `components/chat/`
- `components/reports/`
- `components/stock/`
- `components/asset/`
- `components/chart/`
- `components/layout/`
- `components/providers/`

Import paths all use `@/components/ui/*` already — paths stay the same. Fix prop API differences:

| Component | base-ui API | shadcn API |
|-----------|-------------|------------|
| `Accordion` | `openMultiple` prop | `type="multiple"` prop |
| `Tabs` | `value` / `onValueChange` | identical — no change needed |
| `Badge` | `mergeProps`/`useRender` internals | plain `className` prop via CVA |
| `Button` | base-ui render prop pattern | standard `variant`/`size` CVA props |

### Step 10 — Verify
```bash
pnpm lint
pnpm type-check
```
Both must pass clean. Then do a visual smoke test of accordion, toast, tabs, and button in the running app.

---

## 3. Risk & Edge Cases

### badge.tsx — base-ui internals
`badge.tsx` uses `mergeProps` and `useRender` from base-ui. These are base-ui-specific rendering utilities with no shadcn equivalent. The new badge is a simple CVA-based `<span>` — this is a full rewrite, not a port. No consumer API change expected.

### globals.css — CSS variable merge
shadcn init injects Zinc theme variables and `--radius` into `globals.css`. The existing file may have custom variables. Read `globals.css` first, then append shadcn's injected variables (Zinc palette, `--radius`) below the existing custom variable block. Do not replace the file wholesale.

### Tailwind v4 — no tailwind.config.ts
Tailwind v4 uses CSS-first config. All theme customization (colors, keyframes, animations) goes in `globals.css` via `@theme `. The accordion and toast components require specific keyframes (`accordion-down`, `accordion-up`, `enter`, `leave`). These must be added to `globals.css` as `@keyframes` blocks and referenced via `@theme { --animate-* }` — not via `tailwind.config.ts`.

### Toaster global mount
shadcn's toast system requires `<Toaster />` mounted at the app root. Verify `src/app/layout.tsx` includes it after migration.

---

## 4. Success Criteria

- `@base-ui/react` is not present in `package.json`
- `@radix-ui/react-label` and `@radix-ui/react-toast` are not present as direct deps (managed by shadcn)
- All 10 `components/ui/` files are shadcn-generated new-york style
- `pnpm lint` passes with zero errors
- `pnpm type-check` passes with zero errors
- Accordion, toast, tabs, button, input render correctly in the running app with animations intact
- No visual regressions in `components/chat/`, `components/reports/`, `components/stock/`
