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

require_value() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "$value" || "$value" == --* ]]; then
    fatal "Missing value for $flag"
  fi
}

run_cmd() {
  echo "+ $*"
  "$@"
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
