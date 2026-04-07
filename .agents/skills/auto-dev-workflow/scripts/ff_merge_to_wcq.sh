#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF' >&2
Usage: $0 --branch <feature-branch> --base-sha <sha> --worktree <path>

Verifies that local wcq still matches the recorded base SHA, runs the final gate
against the feature branch tip in a temporary detached worktree, fast-forwards
wcq to the feature branch only after that gate passes, and then removes the
feature worktree + branch.
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

resolve_path() {
  local raw="$1"
  if [[ "$raw" == /* ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s/%s\n' "$repo_root" "$raw"
  fi
}

ensure_repo_worktree_path() {
  local path="$1"
  local top_level=""
  local common_dir=""
  local worktree_branch=""

  [[ -d "$path" ]] || fatal "Worktree path '$path' does not exist."

  top_level="$(git -C "$path" rev-parse --show-toplevel 2>/dev/null || true)"
  common_dir="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"

  if [[ "$top_level" != "$path" || "$common_dir" != "$repo_root/.git" ]]; then
    fatal "Worktree path '$path' does not point to a git worktree in this repository."
  fi

  worktree_branch="$(git -C "$path" symbolic-ref --quiet --short HEAD || true)"
  if [[ -n "${branch:-}" && "$worktree_branch" != "$branch" ]]; then
    fatal "Worktree path '$path' is on branch '${worktree_branch:-detached HEAD}', expected '$branch'."
  fi
}

cleanup_temp_integration() {
  if [[ -n "${temp_worktree:-}" && -d "${temp_worktree:-}" ]]; then
    git worktree remove --force "$temp_worktree" >/dev/null 2>&1 || true
  fi
}

workspace_status_ignoring_worktrees() {
  git status --porcelain --untracked-files=all | grep -vE '^\?\? \.worktrees(/|$)' || true
}

branch=""
base_sha=""
worktree_arg=""
temp_worktree=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      require_value "$1" "${2:-}"
      branch="${2:-}"
      shift 2
      ;;
    --base-sha)
      require_value "$1" "${2:-}"
      base_sha="${2:-}"
      shift 2
      ;;
    --worktree)
      require_value "$1" "${2:-}"
      worktree_arg="${2:-}"
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

if [[ -z "$branch" || -z "$base_sha" || -z "$worktree_arg" ]]; then
  usage
fi

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

git rev-parse --verify "${base_sha}^{commit}" >/dev/null 2>&1 || fatal "Unknown base SHA: $base_sha"
git show-ref --verify --quiet "refs/heads/$branch" || fatal "Branch '$branch' does not exist locally."

feature_worktree=$(resolve_path "$worktree_arg")
if [[ -e "$feature_worktree" ]]; then
  ensure_repo_worktree_path "$feature_worktree"
fi

current_branch=$(git symbolic-ref --quiet --short HEAD || true)
[[ "$current_branch" == "wcq" ]] || fatal "Must run from wcq (currently on ${current_branch:-detached HEAD})."
[[ -z "$(workspace_status_ignoring_worktrees)" ]] || fatal "wcq workspace is dirty; clean it before merging."

current_base=$(git rev-parse wcq)
[[ "$current_base" == "$base_sha" ]] || fatal "Drift detected: wcq has moved from $base_sha to $current_base."

[[ -d "$feature_worktree" ]] || fatal "Worktree path '$feature_worktree' does not exist."
[[ -z "$(git -C "$feature_worktree" status --porcelain --untracked-files=normal)" ]] || fatal "Feature worktree is dirty; clean it before merging."

target_sha="$(git rev-parse "$branch")"
if ! git merge-base --is-ancestor wcq "$target_sha"; then
  fatal "Cannot fast-forward wcq to '$branch'."
fi

timestamp="$(date +%Y%m%d%H%M%S)"
temp_worktree="$repo_root/.worktrees/merge-check-$timestamp-$$"
trap cleanup_temp_integration EXIT

git worktree add --detach "$temp_worktree" "$target_sha" >/dev/null

final_gate_script="$temp_worktree/.agents/skills/auto-dev-workflow/scripts/run_final_gate.sh"
[[ -f "$final_gate_script" ]] || fatal "Final gate script missing from integration worktree: $final_gate_script"

(
  cd "$temp_worktree"
  bash "$final_gate_script" --base-sha "$base_sha"
)

current_target_sha="$(git rev-parse "$branch")"
[[ "$current_target_sha" == "$target_sha" ]] || fatal "Branch '$branch' moved during final gate; rerun integration."

git merge --ff-only "$target_sha" >/dev/null || fatal "Cannot fast-forward wcq to '$branch'."

cleanup_temp_integration
trap - EXIT

git worktree remove "$feature_worktree"
git branch -D "$branch" >/dev/null

printf 'MERGED_BRANCH=%s\n' "$branch"
printf 'MERGE_COMMIT=%s\n' "$(git rev-parse HEAD)"
