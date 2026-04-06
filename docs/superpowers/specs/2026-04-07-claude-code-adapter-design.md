# Claude Code Auto Workflow Adapter Design

**Problem**

The repository-local `auto-dev-workflow` skill is currently written for Codex and Superpowers-native triggers such as `$brainstorming` and `$writing-plans`. Claude Code can execute the underlying Bash workflow scripts just as well, but it does not consume this skill through the same trigger syntax. As a result, the repository has a strong workflow implementation but no Claude Code-native routing or adapter layer.

**Goal**

Add a Claude Code-specific adapter that routes feature and bugfix requests into the existing `auto-dev-workflow` Bash toolchain without polluting the main Codex-oriented `SKILL.md`, while also hardening a few workflow scripts for long-running CLI agent usage.

**Design**

## Scope

- Keep `.agents/skills/auto-dev-workflow/SKILL.md` as the primary Codex/Superpowers entrypoint.
- Add a Claude Code-specific reference document under `.agents/skills/auto-dev-workflow/references/claude-code-adapter.md`.
- Register the Claude adapter through the repository root `CLAUDE.md`.
- Update workflow references so the repository documents platform-specific adapters cleanly.
- Harden selected shell scripts for Claude Code-style repeated Bash execution:
  - `create_feature_workspace.sh`
  - `squash_merge_to_wcq.sh`
- Add or extend smoke tests for the new shell behavior.

## Non-Goals

- Do not rewrite the main `SKILL.md` into a dual-syntax document with both `$skill` and `/command` variants inline.
- Do not replace the existing Codex/Superpowers workflow.
- Do not introduce a Claude Code-specific wrapper binary or new top-level command suite in v1.
- Do not change the default worktree location away from `.worktrees/` in this iteration.

## Architecture

The adapter uses a three-layer design:

1. **Core workflow layer**
   - Existing Bash scripts remain the source of truth for isolated worktree setup, scoped checks, task commits, final gate execution, and squash merge cleanup.
2. **Platform adapter layer**
   - A new `claude-code-adapter.md` explains to Claude Code how to treat the workflow as a Bash contract rather than as a Superpowers skill chain.
3. **Platform routing layer**
   - Root `CLAUDE.md` points Claude Code to the adapter document when the user asks for the auto-dev workflow.

This preserves separation of concerns:
- `SKILL.md` remains optimized for Codex discovery and execution.
- `CLAUDE.md` remains the Claude Code entrypoint.
- Bash scripts remain shared and deterministic.

## Claude Code Adapter Behavior

The new adapter document must instruct Claude Code to:

- Treat `auto-dev-workflow` as a repository-local Bash workflow.
- Avoid searching for or inventing `$skill` syntax.
- Map conceptual phases into direct operational steps:
  - clarify scope
  - create isolated worktree/branch
  - write/update spec and plan docs in the feature worktree
  - use test-first implementation
  - run scoped checks
  - create task commits
  - run final gate
  - squash merge back to `wcq`
- Honor the escape hatch `skip-workflow`.
- Refuse direct edits in the main `wcq` worktree for implementation tasks.

The adapter should explicitly document:
- required scripts
- expected input/output variables from `create_feature_workspace.sh`
- required final gate semantics
- merge/cleanup expectations
- the human-intervention rule when verification keeps failing

## CLAUDE.md Routing

Root `CLAUDE.md` must add a short repository rule that says:

- When the user asks to use the auto-dev workflow for feature or bugfix work, Claude Code must follow `.agents/skills/auto-dev-workflow/references/claude-code-adapter.md`.
- Claude must not edit the main worktree directly for such tasks.
- Claude must use the provided shell scripts rather than improvising its own git workflow.

This routing should be concise and should not duplicate the entire adapter document.

## Script Hardening

### `create_feature_workspace.sh`

Required improvements:

- Run `git worktree prune` before provisioning a new worktree.
- Clean up a stale target directory only when it is clearly orphaned:
  - the directory exists at the intended `.worktrees/<name>` path
  - it is not a live worktree for this repository
  - the matching branch name does not already exist
- Continue to prefer suffixing (`-2`, `-3`, ...) over destructive branch deletion.

Rationale:
- Claude Code is more likely to re-enter workflows after interrupted sessions.
- orphaned directories should not block deterministic setup.
- stale branches should not be deleted automatically without high confidence.

### `squash_merge_to_wcq.sh`

Required improvements:

- Accept an optional explicit final merge message, e.g. `--message "<summary>"`.
- Use the provided message when present; otherwise keep deterministic default message derivation.
- Keep forced cleanup of the feature branch and feature worktree after a successful merge.

Rationale:
- The final squash commit on `wcq` is the durable user-facing history entry.
- Claude Code can summarize task commits better when given an explicit message path.

## Workflow Fail-Safe Rule

Add a documented fail-safe rule for both Codex and Claude Code workflows:

- If `run_scoped_checks.sh` fails twice in a row for the same task, the agent must stop retrying, summarize the failure, and request human intervention instead of looping.

This rule belongs in workflow documentation rather than in shell scripts because it governs agent behavior across platforms.

## Files

### New

- `docs/superpowers/specs/2026-04-07-claude-code-adapter-design.md`
- `docs/superpowers/plans/2026-04-07-claude-code-adapter.md`
- `.agents/skills/auto-dev-workflow/references/claude-code-adapter.md`

### Modified

- `CLAUDE.md`
- `.agents/skills/auto-dev-workflow/SKILL.md`
- `.agents/skills/auto-dev-workflow/references/workflow-contract.md`
- `.agents/skills/auto-dev-workflow/references/gstack-adapter.md`
- `.agents/skills/auto-dev-workflow/scripts/create_feature_workspace.sh`
- `.agents/skills/auto-dev-workflow/scripts/squash_merge_to_wcq.sh`
- `tests/scripts/test_auto_dev_workflow.py`

## Acceptance Criteria

1. Claude Code has an explicit repository-local routing rule in `CLAUDE.md`.
2. The repository contains a Claude Code-specific adapter reference document.
3. The main Codex/Superpowers `SKILL.md` remains Codex-first and does not become a mixed-syntax instruction block.
4. `create_feature_workspace.sh` tolerates interrupted-session residue more safely than before.
5. `squash_merge_to_wcq.sh` supports an explicit merge commit message.
6. The workflow documentation contains a two-strike failure escalation rule for repeated scoped-check failures.
7. Script smoke tests cover the new shell behavior.

## Verification

- Run script smoke tests in `tests/scripts/test_auto_dev_workflow.py`.
- Run Ruff against the changed Python tests.
- Run `quick_validate.py` against `.agents/skills/auto-dev-workflow`.
- Inspect `CLAUDE.md` and `claude-code-adapter.md` together to confirm the routing chain is clear and non-duplicative.
