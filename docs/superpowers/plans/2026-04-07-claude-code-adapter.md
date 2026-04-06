# Claude Code Auto Workflow Adapter Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Claude Code-specific adapter and routing entry for the existing auto-dev workflow, plus small shell hardening changes that make the workflow safer for repeated CLI-agent usage.

**Architecture:** Keep the main `auto-dev-workflow` skill Codex-first, add a Claude-specific adapter reference and `CLAUDE.md` route, and harden only the shared shell scripts that benefit both platforms.

**Tech Stack:** Markdown skill docs, Bash, Git worktrees, pytest, Ruff

---

## Chunk 1: Adapter Docs and Claude Routing

### Task 1: Add the Claude Code adapter reference

**Files:**
- Create: `docs/superpowers/specs/2026-04-07-claude-code-adapter-design.md`
- Create: `.agents/skills/auto-dev-workflow/references/claude-code-adapter.md`

- [ ] **Step 1: Write the adapter reference structure**

Document:
- what triggers the adapter
- the ordered Bash workflow Claude Code must follow
- required scripts and their role
- `skip-workflow`
- no direct edits on `wcq`
- the two-failure escalation rule

- [ ] **Step 2: Keep the adapter Claude-native**

Make sure the document tells Claude Code to treat the workflow as a Bash contract, not as `$skill` invocation syntax.

- [ ] **Step 3: Commit after review**

```bash
git add docs/superpowers/specs/2026-04-07-claude-code-adapter-design.md .agents/skills/auto-dev-workflow/references/claude-code-adapter.md
git commit -m "docs(skill): add claude code adapter reference"
```

### Task 2: Register the adapter in repository routing docs

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.agents/skills/auto-dev-workflow/SKILL.md`
- Modify: `.agents/skills/auto-dev-workflow/references/gstack-adapter.md`
- Modify: `.agents/skills/auto-dev-workflow/references/workflow-contract.md`

- [ ] **Step 1: Add Claude Code routing to `CLAUDE.md`**

Add a concise rule that routes “auto-dev workflow” requests to the adapter document.

- [ ] **Step 2: Update workflow references without polluting the main skill**

Adjust references so:
- `SKILL.md` points to the Claude adapter as a platform-specific companion
- `gstack-adapter.md` remains future-facing
- `workflow-contract.md` mentions the two-strike escalation rule

- [ ] **Step 3: Verify the route is easy to discover**

Run: `rg -n "auto-dev workflow|claude-code-adapter|skip-workflow|two" CLAUDE.md .agents/skills/auto-dev-workflow -S`
Expected: the routing chain and escalation rule are discoverable.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .agents/skills/auto-dev-workflow/SKILL.md .agents/skills/auto-dev-workflow/references/gstack-adapter.md .agents/skills/auto-dev-workflow/references/workflow-contract.md
git commit -m "docs(skill): route claude code through workflow adapter"
```

## Chunk 2: Script Hardening with TDD

### Task 3: Cover interrupted-session workspace setup behavior

**Files:**
- Modify: `tests/scripts/test_auto_dev_workflow.py`
- Modify: `.agents/skills/auto-dev-workflow/scripts/create_feature_workspace.sh`

- [ ] **Step 1: Write a failing smoke test for orphaned target directory cleanup**

Add a test that:
- creates the intended `.worktrees/<branch-name>` directory
- ensures it is not a live git worktree
- runs `create_feature_workspace.sh`
- expects successful reuse/cleanup instead of collision failure

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: FAIL on the new stale-directory scenario.

- [ ] **Step 3: Implement minimal shell changes**

Update `create_feature_workspace.sh` to:
- run `git worktree prune`
- remove only clearly orphaned target directories
- keep non-destructive branch collision handling

- [ ] **Step 4: Run the targeted test suite**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/scripts/test_auto_dev_workflow.py .agents/skills/auto-dev-workflow/scripts/create_feature_workspace.sh
git commit -m "feat(skill): harden feature workspace setup"
```

### Task 4: Cover explicit squash merge messages

**Files:**
- Modify: `tests/scripts/test_auto_dev_workflow.py`
- Modify: `.agents/skills/auto-dev-workflow/scripts/squash_merge_to_wcq.sh`

- [ ] **Step 1: Write a failing smoke test for explicit merge message support**

Add a success-path test that passes `--message "feat(skill): integrate claude adapter"` and asserts that the resulting `wcq` head uses that exact message.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: FAIL because the script does not yet accept `--message`.

- [ ] **Step 3: Implement minimal shell changes**

Update `squash_merge_to_wcq.sh` to:
- parse optional `--message`
- validate it is non-empty when provided
- use the explicit message instead of the derived default

- [ ] **Step 4: Re-run the smoke tests**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/scripts/test_auto_dev_workflow.py .agents/skills/auto-dev-workflow/scripts/squash_merge_to_wcq.sh
git commit -m "feat(skill): support explicit squash merge messages"
```

## Chunk 3: Final Verification

### Task 5: Verify the Claude adapter package end to end

**Files:**
- Verify: `CLAUDE.md`
- Verify: `.agents/skills/auto-dev-workflow/`
- Verify: `tests/scripts/test_auto_dev_workflow.py`

- [ ] **Step 1: Run script smoke tests**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: PASS

- [ ] **Step 2: Run Ruff on the changed Python test file**

Run: `uv run ruff check tests/scripts/test_auto_dev_workflow.py`
Expected: PASS

- [ ] **Step 3: Run format check**

Run: `uv run ruff format --check tests/scripts/test_auto_dev_workflow.py`
Expected: PASS

- [ ] **Step 4: Validate shell syntax**

Run: `for f in .agents/skills/auto-dev-workflow/scripts/*.sh; do bash -n "$f"; done`
Expected: PASS

- [ ] **Step 5: Validate the skill bundle**

Run: `uv run python /home/wcqqq21/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/auto-dev-workflow`
Expected: PASS

- [ ] **Step 6: Commit any remaining documentation cleanup**

```bash
git add CLAUDE.md .agents/skills/auto-dev-workflow docs/superpowers/plans/2026-04-07-claude-code-adapter.md
git commit -m "docs(skill): finalize claude code workflow adapter"
```
