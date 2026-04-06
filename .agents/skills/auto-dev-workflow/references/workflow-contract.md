# Auto Dev Workflow Contract

## Branch & Worktree Naming
- Feature work begins from a clean `wcq` branch only. `wcq` must be local and have no staged or unstaged changes.
- Work branches follow `feat/<yyyymmdd>-<slug>` or `fix/<yyyymmdd>-<slug>` patterns. Slugs are lowercase, hyphen-separated, max 40 characters after normalization, and collisions add `-2`, `-3`, etc.
- Every branch maps to a `.worktrees/<branch-name-with-slash-replaced-by-hyphen>` directory; the workspace is created via `scripts/create_feature_workspace.sh --kind <feat|fix> --slug <slug>`. The script prints `BRANCH_NAME`, `WORKTREE_DIRNAME`, `WORKTREE_PATH`, and `BASE_SHA`.

## Preconditions
- Agents must refuse to start if the current branch is not `wcq` or if the repo has a dirty working tree.
- No edits happen in the `wcq` workspace. All design, plan, and code files are authored inside the feature worktree.
- The workflow stays local: no remote pushes or releases happen in v1.

## Task Execution Policy
- After each plan task is done, run the scoped checks, rerun any task verification commands, and call `scripts/complete_task_commit.sh` with a conventional commit message. That script rejects empty staged diffs plus unstaged or untracked files.
- If `scripts/run_scoped_checks.sh` fails twice in a row for the same task, stop retrying and escalate to the human with a concise failure summary.
- All automated steps within the feature branch must succeed before proceeding. If any script or review reports blocking issues, stop and report the failure.

## Merge & Cleanup
- After the final gate passes, run `scripts/squash_merge_to_wcq.sh --branch <feature-branch> --base-sha <BASE_SHA> --worktree <worktree-path> [--message "<final summary>"]` to verify `wcq` still matches `BASE_SHA`, build the squashed commit in a temporary integration worktree, rerun the final gate on that merged commit, fast-forward `wcq`, and then delete the feature worktree/branch locally.
- Deletion is local only; `wcq` stays clean and points to the merged commit after the script finishes.

## Escape Hatch
- Explicitly remarking `skip-workflow` in the request bypasses this skill only. The request then continues through the normal repository instructions rather than being reclassified as non-implementation work.
- Any other request that involves implementation work must follow this contract.
