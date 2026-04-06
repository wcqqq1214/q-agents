# gstack Adapter Notes

This repository now ships a separate Claude Code adapter in `references/claude-code-adapter.md`. Keep the gstack guidance focused on future gstack execution rather than Claude-specific routing.

This skill ships without `gstack` automation. If a future release requires gstack-based execution, map the existing scripts to gstack tasks as follows:

- `create_feature_workspace.sh` → gstack task that verifies `wcq`, sanitizes slugs, and provisions a worktree.
- `run_scoped_checks.sh`, `complete_task_commit.sh`, and `run_final_gate.sh` → gstack tasks submit deterministic commands (ruff, pytest, pnpm) so the workflow remains reproducible even when the harness executes inside gstack sandboxes.
- `squash_merge_to_wcq.sh` → gstack task that pulls outputs from the feature worktree, reruns the final gate, and performs the local squash merge without pushing upstream.

Until gstack is explicitly required, leave the scripts and documentation in this skill untouched; the adapter note ensures anyone porting the workflow knows which scripts compose each gstack task.
