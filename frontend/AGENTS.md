<!-- BEGIN:nextjs-agent-rules -->
# Frontend Agent Rules

This file applies to all work under `frontend/` and is the canonical agent instruction file for frontend changes.

## Required Reading

Before modifying or generating frontend code, first read and follow these local skill files:

- `frontend/.agents/skills/shadcn/SKILL.md`
- `frontend/.agents/skills/vercel-react-best-practices/AGENTS.md`
- `frontend/.agents/skills/vercel-composition-patterns/AGENTS.md`
- `frontend/.agents/skills/web-design-guidelines/SKILL.md` when doing UI/UX/accessibility review

This preserves the intent of `frontend/CLAUDE.md`: frontend work must follow the local rules under `frontend/.agents/skills/`.

## Next.js Warning

This is NOT the Next.js you know.

This version has breaking changes. APIs, conventions, and file structure may differ from older model knowledge. Read the relevant guide in `node_modules/next/dist/docs/` before writing code and heed deprecation notices.

## Working Rules

- Follow Next.js 16+ conventions and modern React 19 patterns. Do not fall back to outdated React or legacy Next.js APIs.
- Prefer existing `shadcn/ui` components and composition patterns before introducing custom markup.
- When touching shadcn components, use the project's package manager for CLI commands and get fresh component docs before guessing APIs.
- Preserve semantic design tokens and component variants. Avoid raw color styling, manual dark-mode overrides, and ad hoc typography overrides on shared components.
- Use `gap-*` instead of `space-*`, `size-*` when width and height are equal, and `cn()` for conditional classes.
- For forms, follow the `FieldGroup` / `Field` / `InputGroup` patterns instead of raw layout wrappers.
- Prefer compound components and explicit variants over boolean-prop proliferation or render-prop-heavy APIs.
- Eliminate async waterfalls where possible, parallelize independent work, and avoid unnecessary bundle growth or client-side work.
- Respect TypeScript strict mode and ESLint rules. Avoid explicit `any`.
- Frontend API calls target `http://localhost:8080/api/`.

## Review Rules

- When asked to review UI, UX, or accessibility, use `frontend/.agents/skills/web-design-guidelines/SKILL.md` and fetch the latest external guideline source it points to before reviewing.
<!-- END:nextjs-agent-rules -->
