#!/usr/bin/env bash
set -euo pipefail

script_name=$(basename "$0")

usage() {
  cat <<EOF >&2
Usage: $script_name --base-sha <sha>

Runs repository-wide local backend checks (excluding tests/integration) and, when frontend/ changed since <sha>,
frontend lint, Prettier, and type-check gates.
EOF
  exit 1
}

fatal() {
  echo "$1" >&2
  exit 1
}

failure_tail_lines=50
progress_interval_seconds="${WF_PROGRESS_INTERVAL_SECONDS:-5}"

require_value() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    fatal "Missing value for $flag"
  fi
}

render_cmd() {
  local rendered=""
  printf -v rendered '%q ' "$@"
  printf '%s' "${rendered% }"
}

replay_output() {
  local log_path="$1"
  [[ -s "$log_path" ]] || return 0
  cat "$log_path"
}

start_progress_notifier() {
  local command_pid="$1"
  local display="$2"

  (
    local sleeper_pid=""
    trap '[[ -n "$sleeper_pid" ]] && kill "$sleeper_pid" 2>/dev/null || true; exit 0' TERM INT

    while kill -0 "$command_pid" 2>/dev/null; do
      sleep "$progress_interval_seconds" &
      sleeper_pid=$!
      wait "$sleeper_pid" 2>/dev/null || true
      sleeper_pid=""
      if kill -0 "$command_pid" 2>/dev/null; then
        echo "... still running: $display" >&2
      fi
    done
  ) &
}

print_failure_summary() {
  local display="$1"
  local status="$2"
  local log_path="$3"
  local total_lines

  total_lines=$(wc -l < "$log_path")
  total_lines="${total_lines//[[:space:]]/}"

  echo "Command failed with exit code $status: $display" >&2
  if [[ "$total_lines" == "0" ]]; then
    echo "Command produced no output." >&2
    return 0
  fi

  if (( total_lines > failure_tail_lines )); then
    echo "Showing last ${failure_tail_lines} of ${total_lines} log lines." >&2
  else
    echo "Showing all ${total_lines} log lines." >&2
  fi

  tail -n "$failure_tail_lines" "$log_path" >&2
}

run_logged_cmd() {
  local display="$1"
  shift

  local log_path
  local status
  local command_pid
  local notifier_pid=""
  log_path=$(mktemp)

  set +e
  "$@" >"$log_path" 2>&1 &
  command_pid=$!
  start_progress_notifier "$command_pid" "$display"
  notifier_pid=$!
  wait "$command_pid"
  status=$?
  kill "$notifier_pid" 2>/dev/null || true
  wait "$notifier_pid" 2>/dev/null || true
  set -e

  if (( status != 0 )); then
    print_failure_summary "$display" "$status" "$log_path"
    rm -f "$log_path"
    return "$status"
  fi

  replay_output "$log_path"
  rm -f "$log_path"
}

run_cmd() {
  local display
  display=$(render_cmd "$@")
  echo "+ $display"
  run_logged_cmd "$display" "$@"
}

workspace_status_ignoring_worktrees() {
  git status --porcelain --untracked-files=all | grep -vE '^\?\? \.worktrees(/|$)' || true
}

base_sha=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-sha)
      require_value "$1" "${2:-}"
      base_sha="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      fatal "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$base_sha" ]] || fatal "Missing --base-sha"

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

git rev-parse --verify "${base_sha}^{commit}" >/dev/null 2>&1 || fatal "Unknown base SHA: $base_sha"
[[ -z "$(workspace_status_ignoring_worktrees)" ]] || fatal "Workspace is dirty; clean or commit changes before running final gate."

declare -a touched_paths=()
declare -a pytest_targets=()
mapfile -t touched_paths < <(git diff --name-only --diff-filter=ACMRTUXB "$base_sha"..HEAD --)

declare -a python_paths=()
frontend_touched=false
non_test_python_touched=false
for path in "${touched_paths[@]}"; do
  [[ -n "$path" ]] || continue

  case "$path" in
    frontend/*)
      frontend_touched=true
      ;;
    tests/integration/test_*.py|tests/integration/**/test_*.py)
      ;;
    tests/test_*.py|tests/**/test_*.py)
      pytest_targets+=("$path")
      python_paths+=("$path")
      ;;
    *.py|*.pyi)
      python_paths+=("$path")
      non_test_python_touched=true
      ;;
  esac
done

echo "Running local backend gate with integration tests excluded from tests/integration."
if [[ ${#pytest_targets[@]} -gt 0 ]]; then
  for target in "${pytest_targets[@]}"; do
    run_cmd uv run python -m pytest "$target" -q
  done
elif [[ "$non_test_python_touched" == true ]]; then
  fatal "No changed non-integration test files found for backend Python changes."
else
  echo "No changed non-integration test files; skipping pytest gate."
fi

if [[ ${#python_paths[@]} -gt 0 ]]; then
  echo "Running Ruff on ${#python_paths[@]} changed Python path(s)."
  run_cmd uv run ruff check "${python_paths[@]}"
  run_cmd uv run ruff format --check "${python_paths[@]}"
else
  echo "No backend Python paths changed; skipping Ruff path checks."
fi

if [[ "$frontend_touched" == true ]]; then
  echo "Frontend changes detected since $base_sha; running frontend gates."
  (
    cd frontend
    run_cmd pnpm lint
    run_cmd pnpm exec prettier --check .
    run_cmd pnpm type-check
  )
else
  echo "No frontend changes detected since $base_sha; skipping frontend gates."
fi

printf 'BASE_SHA=%s\n' "$base_sha"
printf 'TOUCHED_FILES=%s\n' "${#touched_paths[@]}"
printf 'FRONTEND_CHANGED=%s\n' "$([[ "$frontend_touched" == true ]] && echo yes || echo no)"
