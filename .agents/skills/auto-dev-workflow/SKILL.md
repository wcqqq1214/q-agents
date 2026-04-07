---
name: auto-dev-workflow
description: Use when a request requires implementation work in this repository, including new features, bugfixes, behavior changes, or tooling changes that touch code. Do not use for discussion, planning, explanation, exploration, or review-only requests. If the user explicitly says skip-workflow, bypass this skill and handle the request normally.
---

# Auto Dev Workflow Skill

## When to run
- Implementation requests: new features, bugfixes, behavior adjustments, and tooling/scripts that touch production code.
- **Do not run** for architecture discussion, explanation-only questions, code reviews, or planning artifacts that do not ask for implementation.
- **Escape hatch:** if the user explicitly types `skip-workflow`, exit this skill immediately and continue with normal request handling.

## Required superpowers
- `$brainstorming` to confirm scope and commit the approved design in the feature worktree.
- `$writing-plans` to draft the implementation plan in the same worktree after the design is locked.
- `$using-git-worktrees` to create the `.worktrees/<branch>` workspace from a clean `wcq` branch via `scripts/create_feature_workspace.sh`.
- `$subagent-driven-development` (or `$executing-plans` if subagents are unavailable) for the feature/bugfix implementation loop.
- `$test-driven-development` before adding any production code.
- `$systematic-debugging` before coding on bug fixes to capture the root cause.
- `$requesting-code-review` after each task is implemented and before its commit is created.
- `$verification-before-completion` when claiming a gate has passed (scoped checks, final gate, or merge).

## Core flow
1. **Preflight:** Ensure the main workspace is on a clean `wcq`. Run `scripts/create_feature_workspace.sh --kind <feat|fix> --slug <topic-slug>` to capture `BASE_SHA`, branch name, and worktree path; this enforces branch/worktree naming, slug normalization, and clean-state requirements.
2. **Design & plan:** Inside the feature worktree, run the approved `$brainstorming` loop, write the spec to `docs/superpowers/specs/…`, dispatch the spec-reviewer, then run `$writing-plans` to create `docs/superpowers/plans/…` before moving to implementation. Keep the spec+plan in the feature worktree so the docs travel with the branch.
3. **Task loop:** For each plan step:
   - If the task fixes a bug, run `$systematic-debugging` to investigate the root cause before touching code.
   - Drive the change with `$test-driven-development` (red → green → refactor) and confirm the failing test captures the desired behavior.
   - Run `scripts/run_scoped_checks.sh --base-sha <BASE_SHA> --diff-target cached|worktree --cmd '<task verification command>' …` to invoke the path-based lint/format/type checks plus any caller-provided commands described in the verification matrix.
   - Run a spec compliance review against the approved plan or spec. Do not commit until the reviewer confirms the task matches the requested scope.
   - Run `$requesting-code-review` for code quality, resolve any blocking issues, and only then call `scripts/complete_task_commit.sh --message '<conventional commit>' --cmd '…'`. The script rejects empty staged diffs and unstaged changes.
4. **Final gate:** Use `scripts/run_final_gate.sh --base-sha <BASE_SHA>` to run the local backend suite (sequential `uv run python -m pytest <each-changed-non-integration-test-file> -q`, then path-scoped `uv run ruff check <changed-python-paths>` and `uv run ruff format --check <changed-python-paths>`). If backend Python changed but no non-integration test file changed with it, the gate fails immediately. When `frontend/` changed since `<BASE_SHA>`, the script also runs `pnpm lint`, `pnpm exec prettier --check .`, and `pnpm type-check`. Run `$verification-before-completion` on the final gate command output before claiming success.
5. **Merge & clean:** Run `scripts/ff_merge_to_wcq.sh --branch <feature-branch> --base-sha <BASE_SHA> --worktree <path>` to confirm `wcq` has not drifted, validate the feature branch tip in a temporary detached integration worktree, rerun the final gate on that exact commit, fast-forward `wcq`, and delete the feature branch/worktree locally.

## Scripts at your disposal
- `scripts/create_feature_workspace.sh` – validates clean `wcq`, derives branch/worktree names, and prints `BASE_SHA`, `BRANCH_NAME`, and `WORKTREE_PATH`.
- `scripts/run_scoped_checks.sh` – runs path-based ruff/pnpm lint/prettier/type-check commands plus caller-provided `--cmd`s for each task.
- `scripts/complete_task_commit.sh` – reruns task-specific commands, enforces staged changes only, and commits with the provided conventional message.
- `scripts/run_final_gate.sh` – executes backend checks every time and frontend checks only if `frontend/` changed relative to `<BASE_SHA>`.
- `scripts/ff_merge_to_wcq.sh` – ensures `wcq` still matches `<BASE_SHA>`, validates the feature branch tip in a temporary detached integration worktree, fast-forwards `wcq`, and tears down the feature branch/worktree.

## References
- Branch/worktree naming, `skip-workflow` policy, and merge expectations live in `references/workflow-contract.md`.
- The scoped check and final gate command matrix (including ESLint and Prettier) lives in `references/verification-matrix.md`.
- Claude Code routing lives in repository `CLAUDE.md` and `references/claude-code-adapter.md`; keep this `SKILL.md` Codex-first.
- Future gstack adapter expectations are captured in `references/gstack-adapter.md` so the workflow can be mapped later without changing the current scripts.

## Notes
- Do not push to remotes; the workflow stays local until the feature is merged into `wcq`.
- Keep the feature worktree isolated: all editing, testing, spec writing, planning, and committing happen there before `ff_merge_to_wcq.sh` touches `wcq`.
- If `scripts/run_scoped_checks.sh` fails twice in a row for the same task, stop retrying and ask the human for direction instead of looping.
