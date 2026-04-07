# Claude Code Adapter

Use this adapter when Claude Code is asked to implement a feature or bugfix with the repository's `auto-dev workflow`.

## Purpose

Claude Code should treat the workflow as a Bash contract built on repository-local scripts. Do not look for Superpowers `$skill` syntax here. The Codex-facing `SKILL.md` remains the canonical skill entrypoint for Codex; this adapter translates the same workflow into Claude Code-native behavior.

## Trigger

Apply this adapter when the user asks to:
- use the `auto-dev workflow`
- follow the repository workflow for a feature or bugfix
- implement a change while keeping `wcq` untouched until merge

If the user explicitly says `skip-workflow`, do not use this adapter.

## Hard Rules

- Never implement directly in the main `wcq` worktree.
- Use the provided shell scripts instead of inventing a custom git workflow.
- Keep all design docs, plans, code edits, tests, and commits inside the feature worktree.
- Stop and escalate if `scripts/run_scoped_checks.sh` fails twice in a row for the same task.

## Claude Code Execution Model

Treat the workflow as this ordered Bash sequence:

1. Clarify scope and confirm the change.
2. Run `scripts/create_feature_workspace.sh --kind <feat|fix> --slug <topic>`.
3. Read the emitted values:
   - `BRANCH_NAME`
   - `WORKTREE_DIRNAME`
   - `WORKTREE_PATH`
   - `BASE_SHA`
4. Switch work to `WORKTREE_PATH`.
5. Write or update the design doc and implementation plan in that feature worktree.
6. Implement each task with test-first changes.
7. Run `scripts/run_scoped_checks.sh --base-sha <BASE_SHA> --diff-target cached|worktree --cmd '<task check>' ...`.
8. Stage the finished task and commit it with `scripts/complete_task_commit.sh --message '<conventional commit>' --cmd '...'`.
9. After all tasks pass, run `scripts/run_final_gate.sh --base-sha <BASE_SHA>`.
10. Merge with `scripts/ff_merge_to_wcq.sh --branch <BRANCH_NAME> --base-sha <BASE_SHA> --worktree <WORKTREE_PATH>`.

## Script Notes

### `create_feature_workspace.sh`

- Must be run from a clean `wcq` worktree.
- Creates a dedicated branch and worktree under `.worktrees/`.
- Reuses the intended target path when the directory is orphaned residue from an interrupted run.

### `run_scoped_checks.sh`

- Use it for per-task checks, not the whole feature gate.
- Pass task-specific verification commands with repeated `--cmd`.
- If the same task hits two consecutive failures, stop retrying and ask the human what to do next.

### `complete_task_commit.sh`

- Only call it after staging the finished task.
- It refuses empty staged diffs or dirty unstaged state.

### `run_final_gate.sh`

- Runs local backend checks every time with `tests/integration` excluded.
- Executes changed non-integration pytest files one by one to keep the local gate stable under resource limits.
- Fails fast if backend Python changes do not come with changed non-integration tests.
- Runs Ruff only against backend Python files changed since `BASE_SHA`.
- Adds frontend lint, Prettier, and type-check only when `frontend/` changed.

### `ff_merge_to_wcq.sh`

- Must be run from clean `wcq`.
- Refuses drifted base state.
- Refuses feature branches that cannot be fast-forwarded from `wcq`.
- Runs the final gate in a detached worktree at the feature branch tip before updating `wcq`.
- Cleans up the feature worktree and feature branch on success.

## Escalation Rule

Escalate to the human when:
- scoped checks fail twice in a row for the same task
- the final gate fails and the fix is unclear
- the feature branch cannot be fast-forwarded cleanly and the fix path is unclear
- the requested behavior contradicts this repository contract
