# Gate Log Truncation Implementation Plan

> **For agentic workers:** REQUIRED: Use $subagent-driven-development (if subagents available) or $executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tail-only failure-log output to the workflow scoped-check and final-gate scripts.

**Architecture:** Drive the change with script-level regression tests that force stubbed verification commands to emit oversized failure logs. Then add a small Bash helper in each script that captures command output, replays full logs on success, truncates failures to the last 50 lines, and emits lightweight progress notices while long-running commands are still active.

**Tech Stack:** Bash, git workflow scripts, pytest script tests

---

## Chunk 1: Scoped Checks Failure Output

### Task 1: Reproduce oversized scoped-check failure logs

**Files:**
- Modify: `tests/scripts/test_auto_dev_workflow.py`
- Test: `tests/scripts/test_auto_dev_workflow.py`

- [ ] **Step 1: Write the failing test**

Add a scoped-checks regression that stages a backend Python change, configures the `uv` stub to emit 120 failure lines for `ruff check`, and asserts stderr shows only the tail plus a truncation notice.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: FAIL because `run_scoped_checks.sh` currently prints the full command log instead of a truncated tail.

- [ ] **Step 3: Write minimal implementation**

Update `run_scoped_checks.sh` so all command helpers capture output, replay it on success, and show only the last 50 lines when a command fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: PASS for the new scoped-checks regression.

## Chunk 2: Final Gate Failure Output

### Task 2: Reproduce oversized final-gate failure logs

**Files:**
- Modify: `tests/scripts/test_auto_dev_workflow.py`
- Modify: `.agents/skills/auto-dev-workflow/scripts/run_final_gate.sh`
- Test: `tests/scripts/test_auto_dev_workflow.py`

- [ ] **Step 1: Write the failing test**

Add a final-gate regression that commits a changed backend module plus test file, configures the `uv` stub to emit 120 failure lines for `python -m pytest`, and asserts stderr shows only the tail plus a truncation notice.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: FAIL because `run_final_gate.sh` currently prints the full command log instead of a truncated tail.

- [ ] **Step 3: Write minimal implementation**

Update `run_final_gate.sh` with the same capture-and-tail failure helper used for scoped checks.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q`
Expected: PASS for the new final-gate regression.

- [ ] **Step 5: Run focused verification**

Run: `bash .agents/skills/auto-dev-workflow/scripts/run_scoped_checks.sh --base-sha <BASE_SHA> --diff-target worktree --cmd 'uv run python -m pytest tests/scripts/test_auto_dev_workflow.py -q'`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-04-07-gate-log-truncation-design.md \
        docs/superpowers/plans/2026-04-07-gate-log-truncation.md \
        tests/scripts/test_auto_dev_workflow.py \
        .agents/skills/auto-dev-workflow/scripts/run_scoped_checks.sh \
        .agents/skills/auto-dev-workflow/scripts/run_final_gate.sh
git commit -m "fix(skill): truncate gate failure logs"
```
