#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF >&2
Usage: $(basename "$0") --base-sha <sha> [--diff-target cached|worktree] [--cmd "<command>"]...

Options:
  --base-sha <sha>              Recorded feature-branch base SHA for workflow validation (required)
  --diff-target cached|worktree Inspect staged changes or the working tree. Default: cached
  --cmd "<command>"             Additional verification command to run (repeatable)
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

run_array_cmd() {
  local display
  display=$(render_cmd "$@")
  printf '+ %s\n' "$display"
  run_logged_cmd "$display" "$@"
}

run_shell_cmd() {
  local cmd="$1"
  printf '+ %s\n' "$cmd"
  run_logged_cmd "$cmd" bash -c "$cmd"
}

run_frontend_cmd() {
  local cmd="$1"
  local display="(cd frontend && $cmd)"
  printf '+ %s\n' "$display"
  run_logged_cmd "$display" bash -c "cd frontend && $cmd"
}

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

base_sha=""
diff_target="cached"
declare -a user_cmds=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-sha)
      require_value "$1" "${2:-}"
      base_sha="${2:-}"
      shift 2
      ;;
    --diff-target)
      require_value "$1" "${2:-}"
      diff_target="${2:-}"
      shift 2
      ;;
    --cmd)
      require_value "$1" "${2:-}"
      user_cmds+=("${2:-}")
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
[[ "$diff_target" == "cached" || "$diff_target" == "worktree" ]] || fatal "--diff-target must be cached or worktree."
git rev-parse --verify "${base_sha}^{commit}" >/dev/null 2>&1 || fatal "Unknown base SHA: $base_sha"
git merge-base --is-ancestor "$base_sha" HEAD >/dev/null 2>&1 || fatal "Base SHA $base_sha is not an ancestor of HEAD."

declare -a touched_paths=()
if [[ "$diff_target" == "cached" ]]; then
  mapfile -t touched_paths < <(git diff --cached --name-only --diff-filter=ACMRTUXB "$base_sha" --)
else
  mapfile -t touched_paths < <(
    {
      git diff --name-only --diff-filter=ACMRTUXB "$base_sha" --
      git ls-files --others --exclude-standard
    } | awk 'NF && !seen[$0]++'
  )
fi

declare -a python_paths=()
frontend_touched=false
typecheck_needed=false

for path in "${touched_paths[@]}"; do
  [[ -n "$path" ]] || continue

  case "$path" in
    frontend/*)
      frontend_touched=true
      ;;
    *.py|*.pyi)
      python_paths+=("$path")
      ;;
  esac

  case "$path" in
    frontend/*.ts|frontend/*.tsx|frontend/**/*.ts|frontend/**/*.tsx|frontend/package.json|frontend/pnpm-lock.yaml|frontend/tsconfig*.json|frontend/next-env.d.ts|frontend/eslint.config.*|frontend/.eslintrc*|frontend/prettier.config.*|frontend/.prettierrc*)
      typecheck_needed=true
      ;;
  esac
done

if [[ ${#python_paths[@]} -gt 0 ]]; then
  echo "Running Ruff on ${#python_paths[@]} Python path(s)."
  run_array_cmd uv run ruff check "${python_paths[@]}"
  run_array_cmd uv run ruff format --check "${python_paths[@]}"
else
  echo "No backend Python paths changed; skipping Ruff path checks."
fi

for cmd in "${user_cmds[@]}"; do
  run_shell_cmd "$cmd"
done

if [[ "$frontend_touched" == true ]]; then
  echo "Frontend changes detected; running lint and Prettier."
  run_frontend_cmd "pnpm lint"
  run_frontend_cmd "pnpm exec prettier --check ."

  if [[ "$typecheck_needed" == true ]]; then
    run_frontend_cmd "pnpm type-check"
  else
    echo "Frontend type-check gate not triggered."
  fi
else
  echo "No frontend changes detected; skipping frontend gates."
fi

printf 'BASE_SHA=%s\n' "$base_sha"
printf 'DIFF_TARGET=%s\n' "$diff_target"
printf 'TOUCHED_FILES=%s\n' "${#touched_paths[@]}"
printf 'PYTHON_GUARD=%s\n' "$([[ ${#python_paths[@]} -gt 0 ]] && echo yes || echo no)"
printf 'FRONTEND_GUARD=%s\n' "$([[ "$frontend_touched" == true ]] && echo yes || echo no)"
printf 'TYPECHECK=%s\n' "$([[ "$typecheck_needed" == true ]] && echo yes || echo no)"
printf 'CMD_COUNT=%s\n' "${#user_cmds[@]}"
