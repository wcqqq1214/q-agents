#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF' >&2
Usage: $0 --branch <feature-branch> --base-sha <sha> --worktree <path> [--message "<summary>"]

Squash merges a verified feature branch back into local wcq, reruns the final
gate on the merged commit in a temporary integration worktree, fast-forwards
wcq only after that gate passes, and then removes the feature worktree + branch.
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

derive_commit_message() {
  local branch_name="$1"
  local kind="${branch_name%%/*}"
  local slug="$branch_name"

  if [[ "$branch_name" == */* ]]; then
    slug="${branch_name#*/}"
    slug="${slug#*-}"
  fi

  [[ -n "$slug" ]] || slug="${branch_name//\//-}"

  case "$kind" in
    feat)
      printf 'feat: squash merge %s' "$slug"
      ;;
    fix)
      printf 'fix: squash merge %s' "$slug"
      ;;
    *)
      printf 'chore: squash merge %s' "${branch_name//\//-}"
      ;;
  esac
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

  if [[ -n "${temp_branch:-}" ]] && git show-ref --verify --quiet "refs/heads/$temp_branch"; then
    git branch -D "$temp_branch" >/dev/null 2>&1 || true
  fi
}

workspace_status_ignoring_worktrees() {
  git status --porcelain --untracked-files=all | grep -vE '^\?\? \.worktrees(/|$)' || true
}

branch=""
base_sha=""
worktree_arg=""
message=""
temp_branch=""
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
    --message)
      require_value "$1" "${2:-}"
      message="${2:-}"
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

timestamp="$(date +%Y%m%d%H%M%S)"
temp_branch="merge-check-$timestamp-$$"
temp_worktree="$repo_root/.worktrees/$temp_branch"
trap cleanup_temp_integration EXIT

git worktree add -b "$temp_branch" "$temp_worktree" wcq >/dev/null

if ! git -C "$temp_worktree" merge --squash "$branch"; then
  fatal "Merge conflicts encountered while squashing '$branch' into the integration worktree."
fi

if git -C "$temp_worktree" diff --cached --quiet --ignore-submodules --; then
  fatal "Squash merge produced no staged changes."
fi

merge_message="$message"
if [[ -z "$merge_message" ]]; then
  merge_message="$(derive_commit_message "$branch")"
fi
git -C "$temp_worktree" commit -m "$merge_message" >/dev/null

final_gate_script="$temp_worktree/.agents/skills/auto-dev-workflow/scripts/run_final_gate.sh"
[[ -f "$final_gate_script" ]] || fatal "Final gate script missing from merged worktree: $final_gate_script"

(
  cd "$temp_worktree"
  bash "$final_gate_script" --base-sha "$base_sha"
)

git merge --ff-only "$temp_branch" >/dev/null

cleanup_temp_integration
trap - EXIT

git worktree remove "$feature_worktree"
git branch -D "$branch" >/dev/null

printf 'MERGED_BRANCH=%s\n' "$branch"
printf 'MERGE_COMMIT=%s\n' "$(git rev-parse HEAD)"
