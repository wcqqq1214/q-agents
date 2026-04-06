# Gate Log Truncation Design

## Goal

When `run_scoped_checks.sh` or `run_final_gate.sh` executes a failing verification command, the script should avoid dumping the entire captured log and instead emit a compact failure summary with only the last 50 lines.

## Scope

- Touch only the two workflow gate scripts plus their script-level tests and implementation docs.
- Keep the existing gate-selection rules, execution order, and stop-on-first-failure behavior unchanged.
- Do not add retries, parallel execution, or new workflow inputs.

## Design

Both scripts already funnel all verification through small shell helpers. Extend those helpers so each command runs with stdout and stderr captured into a temporary log file. On success, replay the captured output so successful commands remain fully visible.

On failure, print:

1. the command that failed
2. its exit code
3. a truncation notice when the captured output exceeds 50 lines
4. only the last 50 lines of the captured output

Because the output is being captured for possible truncation, long-running commands should also emit lightweight `still running` progress notices so the workflow does not look hung while the command is active.

`run_scoped_checks.sh` needs this behavior for array commands, extra `--cmd` shell commands, and frontend subcommands. `run_final_gate.sh` needs the same behavior for every sequential gate command.

## Testing

Add two regression tests in `tests/scripts/test_auto_dev_workflow.py`:

1. make the scoped-checks `uv run ruff check ...` stub emit 120 lines and fail, then assert stderr contains the truncation notice plus the tail lines only
2. make the final-gate `uv run python -m pytest ...` stub emit 120 lines and fail, then assert the same tail-only behavior
