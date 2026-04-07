"""Smoke tests for the repository-local auto dev workflow scripts."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_ROOT = (
    Path(__file__).resolve().parents[2] / ".agents" / "skills" / "auto-dev-workflow" / "scripts"
)


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=repo)


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _script_path(script_name: str) -> Path:
    source = SCRIPT_ROOT / script_name
    assert source.exists(), f"missing workflow script: {source}"
    return source


def _install_command_stubs(
    repo: Path,
    log_path: Path,
    *,
    fail_pattern: str | None = None,
    fail_lines: int = 0,
    fail_code: int = 1,
    success_pattern: str | None = None,
    success_output: str | None = None,
    success_sleep: float | None = None,
) -> dict[str, str]:
    bin_dir = log_path.parent / "test-bin"
    bin_dir.mkdir()

    stub = """#!/usr/bin/env bash
set -euo pipefail
printf '%s %s\n' "$(basename "$0")" "$*" >> "$WF_LOG"
if [[ -n "${WF_FAIL_PATTERN:-}" && "$*" == *"${WF_FAIL_PATTERN}"* ]]; then
  i=1
  while (( i <= ${WF_FAIL_LINES:-0} )); do
    printf 'FAIL_LINE_%03d %s\n' "$i" "$*" >&2
    i=$((i + 1))
  done
  exit "${WF_FAIL_CODE:-1}"
fi
if [[ -n "${WF_SUCCESS_PATTERN:-}" && "$*" == *"${WF_SUCCESS_PATTERN}"* ]]; then
  if [[ -n "${WF_SUCCESS_SLEEP:-}" ]]; then
    sleep "${WF_SUCCESS_SLEEP}"
  fi
  if [[ -n "${WF_SUCCESS_OUTPUT:-}" ]]; then
    printf '%s\n' "${WF_SUCCESS_OUTPUT}"
  fi
fi
"""
    _write_executable(bin_dir / "uv", stub)
    _write_executable(bin_dir / "pnpm", stub)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["WF_LOG"] = str(log_path)
    if fail_pattern is not None:
        env["WF_FAIL_PATTERN"] = fail_pattern
        env["WF_FAIL_LINES"] = str(fail_lines)
        env["WF_FAIL_CODE"] = str(fail_code)
    if success_pattern is not None:
        env["WF_SUCCESS_PATTERN"] = success_pattern
    if success_output is not None:
        env["WF_SUCCESS_OUTPUT"] = success_output
    if success_sleep is not None:
        env["WF_SUCCESS_SLEEP"] = str(success_sleep)
    return env


def _install_repo_local_final_gate_stub(repo: Path) -> None:
    _write_executable(
        repo / ".agents" / "skills" / "auto-dev-workflow" / "scripts" / "run_final_gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    init_result = _git(repo, "init")
    assert init_result.returncode == 0, init_result.stderr
    checkout_result = _git(repo, "checkout", "-b", "wcq")
    assert checkout_result.returncode == 0, checkout_result.stderr
    assert _git(repo, "config", "user.email", "tests@example.com").returncode == 0
    assert _git(repo, "config", "user.name", "Workflow Tests").returncode == 0

    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    (repo / "app").mkdir()
    (repo / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_smoke() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    (repo / "frontend" / "src" / "app").mkdir(parents=True)
    (repo / "frontend" / "package.json").write_text('{"name":"frontend"}\n', encoding="utf-8")
    (repo / "frontend" / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (repo / "frontend" / ".prettierrc").write_text("{}\n", encoding="utf-8")
    (repo / "frontend" / "eslint.config.mjs").write_text("export default [];\n", encoding="utf-8")
    (repo / "frontend" / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return <div />; }\n",
        encoding="utf-8",
    )

    add_result = _git(repo, "add", ".")
    assert add_result.returncode == 0, add_result.stderr
    commit_result = _git(repo, "commit", "-m", "chore: seed repo")
    assert commit_result.returncode == 0, commit_result.stderr
    return repo


def test_create_feature_workspace_creates_branch_and_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("create_feature_workspace.sh")

    result = _run(
        ["bash", str(script), "--kind", "feat", "--slug", "Auto Workflow"],
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr

    values = dict(line.split("=", maxsplit=1) for line in result.stdout.splitlines() if "=" in line)
    assert re.fullmatch(r"feat/\d{8}-auto-workflow", values["BRANCH_NAME"])
    assert values["WORKTREE_DIRNAME"] == values["BRANCH_NAME"].replace("/", "-")
    assert Path(values["WORKTREE_PATH"]).is_dir()

    branch_result = _run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=Path(values["WORKTREE_PATH"]),
    )
    assert branch_result.returncode == 0, branch_result.stderr
    assert branch_result.stdout.strip() == values["BRANCH_NAME"]


def test_create_feature_workspace_refuses_dirty_workspace(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("create_feature_workspace.sh")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")

    result = _run(
        ["bash", str(script), "--kind", "feat", "--slug", "Auto Workflow"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Workspace contains uncommitted changes" in result.stderr


def test_create_feature_workspace_requires_argument_value(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("create_feature_workspace.sh")

    result = _run(
        ["bash", str(script), "--kind"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Missing value for --kind" in result.stderr


def test_create_feature_workspace_reuses_orphaned_target_directory(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("create_feature_workspace.sh")
    date_stamp = datetime.now().strftime("%Y%m%d")
    target_path = repo / ".worktrees" / f"feat-{date_stamp}-stale-dir"
    target_path.mkdir(parents=True)
    (target_path / "orphaned.txt").write_text("leftover\n", encoding="utf-8")

    result = _run(
        ["bash", str(script), "--kind", "feat", "--slug", "Stale Dir"],
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", maxsplit=1) for line in result.stdout.splitlines() if "=" in line)
    assert values["WORKTREE_PATH"] == str(target_path)
    assert not (target_path / "orphaned.txt").exists()


def test_run_scoped_checks_cached_ignores_unstaged_frontend_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")
    log_path = tmp_path / "commands.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _git(repo, "add", "app/module.py").returncode == 0
    (repo / "frontend" / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return <main />; }\n",
        encoding="utf-8",
    )

    result = _run(
        [
            "bash",
            str(script),
            "--base-sha",
            base_sha,
            "--diff-target",
            "cached",
            "--cmd",
            "printf 'task-check\\n' >> \"$WF_LOG\"",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "uv run ruff check app/module.py" in log_text
    assert "uv run ruff format --check app/module.py" in log_text
    assert "task-check" in log_text
    assert "pnpm lint" not in log_text
    assert "pnpm exec prettier --check ." not in log_text
    assert "pnpm type-check" not in log_text


def test_run_scoped_checks_requires_argument_value(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")

    result = _run(
        ["bash", str(script), "--base-sha"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Missing value for --base-sha" in result.stderr


def test_run_scoped_checks_truncates_failing_command_output(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")
    log_path = tmp_path / "commands.log"
    env = _install_command_stubs(
        repo,
        log_path,
        fail_pattern="ruff check",
        fail_lines=120,
    )
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _git(repo, "add", "app/module.py").returncode == 0

    result = _run(
        [
            "bash",
            str(script),
            "--base-sha",
            base_sha,
            "--diff-target",
            "cached",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode != 0
    assert "Showing last 50 of 120 log lines." in result.stderr
    assert "FAIL_LINE_001" not in result.stderr
    assert "FAIL_LINE_070" not in result.stderr
    assert "FAIL_LINE_071" in result.stderr
    assert "FAIL_LINE_120" in result.stderr
    assert "uv run ruff check app/module.py" in log_path.read_text(encoding="utf-8")


def test_run_scoped_checks_replays_successful_command_output(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")
    log_path = tmp_path / "commands.log"
    env = _install_command_stubs(
        repo,
        log_path,
        success_pattern="ruff check",
        success_output="SCOPED_OK_1\nSCOPED_OK_2",
    )
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _git(repo, "add", "app/module.py").returncode == 0

    result = _run(
        [
            "bash",
            str(script),
            "--base-sha",
            base_sha,
            "--diff-target",
            "cached",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "SCOPED_OK_1\nSCOPED_OK_2" in result.stdout


def test_run_scoped_checks_worktree_detects_unstaged_frontend_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")
    log_path = tmp_path / "commands.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "frontend" / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return <section />; }\n",
        encoding="utf-8",
    )

    result = _run(
        [
            "bash",
            str(script),
            "--base-sha",
            base_sha,
            "--diff-target",
            "worktree",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "pnpm lint" in log_text
    assert "pnpm exec prettier --check ." in log_text
    assert "pnpm type-check" in log_text


def test_run_scoped_checks_worktree_detects_untracked_frontend_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_scoped_checks.sh")
    log_path = tmp_path / "commands.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "frontend" / "src" / "app" / "new-page.tsx").write_text(
        "export default function NewPage() { return <aside />; }\n",
        encoding="utf-8",
    )

    result = _run(
        [
            "bash",
            str(script),
            "--base-sha",
            base_sha,
            "--diff-target",
            "worktree",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "pnpm lint" in log_text
    assert "pnpm exec prettier --check ." in log_text
    assert "pnpm type-check" in log_text


def test_complete_task_commit_refuses_empty_staged_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("complete_task_commit.sh")

    result = _run(
        ["bash", str(script), "--message", "feat(skill): demo"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "No staged changes" in result.stderr


def test_complete_task_commit_requires_argument_value(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("complete_task_commit.sh")

    result = _run(
        ["bash", str(script), "--message"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Missing value for --message" in result.stderr


def test_complete_task_commit_reruns_checks_and_commits(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("complete_task_commit.sh")
    log_path = tmp_path / "task-commit.log"
    env = os.environ.copy()
    env["WF_LOG"] = str(log_path)

    (repo / "README.md").write_text("task complete\n", encoding="utf-8")
    assert _git(repo, "add", "README.md").returncode == 0

    result = _run(
        [
            "bash",
            str(script),
            "--message",
            "feat(skill): commit task",
            "--cmd",
            "printf 'task-verified\\n' >> \"$WF_LOG\"",
        ],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert log_path.read_text(encoding="utf-8") == "task-verified\n"

    log_result = _git(repo, "log", "-1", "--pretty=%s")
    assert log_result.returncode == 0, log_result.stderr
    assert log_result.stdout.strip() == "feat(skill): commit task"


def test_run_final_gate_includes_frontend_checks_when_frontend_changed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "frontend" / "src" / "app" / "page.tsx").write_text(
        "export default function Page() { return <article />; }\n",
        encoding="utf-8",
    )
    assert _git(repo, "add", "frontend/src/app/page.tsx").returncode == 0
    commit_result = _git(repo, "commit", "-m", "feat(frontend): update page")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "uv run python -m pytest" not in log_text
    assert "uv run ruff check" not in log_text
    assert "uv run ruff format --check" not in log_text
    assert "pnpm lint" in log_text
    assert "pnpm exec prettier --check ." in log_text
    assert "pnpm type-check" in log_text


def test_run_final_gate_scopes_ruff_to_changed_backend_python_paths(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_smoke() -> None:\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    assert _git(repo, "add", "app/module.py", "tests/test_smoke.py").returncode == 0
    commit_result = _git(repo, "commit", "-m", "feat(app): update module")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8")
    assert "uv run python -m pytest tests/test_smoke.py -q" in log_text
    assert "uv run ruff check app/module.py tests/test_smoke.py" in log_text
    assert "uv run ruff format --check app/module.py tests/test_smoke.py" in log_text
    assert "pnpm lint" not in log_text
    assert "pnpm exec prettier --check ." not in log_text
    assert "pnpm type-check" not in log_text


def test_run_final_gate_requires_changed_tests_for_backend_python_paths(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert _git(repo, "add", "app/module.py").returncode == 0
    commit_result = _git(repo, "commit", "-m", "feat(app): update module")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode != 0
    assert "No changed non-integration test files found" in result.stderr


def test_run_final_gate_requires_argument_value(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")

    result = _run(
        ["bash", str(script), "--base-sha"],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Missing value for --base-sha" in result.stderr


def test_run_final_gate_truncates_failing_command_output(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(
        repo,
        log_path,
        fail_pattern="python -m pytest",
        fail_lines=120,
    )
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_smoke() -> None:\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    assert _git(repo, "add", "app/module.py", "tests/test_smoke.py").returncode == 0
    commit_result = _git(repo, "commit", "-m", "feat(app): update module")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode != 0
    assert "Showing last 50 of 120 log lines." in result.stderr
    assert "FAIL_LINE_001" not in result.stderr
    assert "FAIL_LINE_070" not in result.stderr
    assert "FAIL_LINE_071" in result.stderr
    assert "FAIL_LINE_120" in result.stderr
    assert "uv run python -m pytest tests/test_smoke.py -q" in log_path.read_text(encoding="utf-8")


def test_run_final_gate_replays_successful_command_output(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(
        repo,
        log_path,
        success_pattern="python -m pytest",
        success_output="PYTEST_OK_1\nPYTEST_OK_2",
    )
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "app" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repo / "tests" / "test_smoke.py").write_text(
        "def test_smoke() -> None:\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    assert _git(repo, "add", "app/module.py", "tests/test_smoke.py").returncode == 0
    commit_result = _git(repo, "commit", "-m", "feat(app): update module")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "PYTEST_OK_1\nPYTEST_OK_2" in result.stdout


def test_run_final_gate_refuses_dirty_workspace(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("run_final_gate.sh")
    log_path = tmp_path / "final-gate.log"
    env = _install_command_stubs(repo, log_path)
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "README.md").write_text("dirty workspace\n", encoding="utf-8")

    result = _run(
        ["bash", str(script), "--base-sha", base_sha],
        cwd=repo,
        env=env,
    )

    assert result.returncode != 0
    assert "Workspace is dirty" in result.stderr


def test_ff_merge_to_wcq_refuses_drifted_base(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("ff_merge_to_wcq.sh")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "checkout", "-b", "feat/20260407-demo").returncode == 0
    (repo / "README.md").write_text("feature branch\n", encoding="utf-8")
    assert _git(repo, "add", "README.md").returncode == 0
    assert _git(repo, "commit", "-m", "feat: branch change").returncode == 0
    assert _git(repo, "checkout", "wcq").returncode == 0

    (repo / "README.md").write_text("wcq drift\n", encoding="utf-8")
    assert _git(repo, "add", "README.md").returncode == 0
    assert _git(repo, "commit", "-m", "chore: drift wcq").returncode == 0

    result = _run(
        [
            "bash",
            str(script),
            "--branch",
            "feat/20260407-demo",
            "--base-sha",
            base_sha,
            "--worktree",
            str(tmp_path / "missing-worktree"),
        ],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Drift detected" in result.stderr


def test_ff_merge_to_wcq_rejects_non_git_worktree_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _install_repo_local_final_gate_stub(repo)
    script = _script_path("ff_merge_to_wcq.sh")
    assert (
        _git(repo, "add", ".agents/skills/auto-dev-workflow/scripts/run_final_gate.sh").returncode
        == 0
    )
    assert _git(repo, "commit", "-m", "chore: add final gate stub").returncode == 0
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert _git(repo, "checkout", "-b", "feat/20260407-demo").returncode == 0
    (repo / "README.md").write_text("feature branch\n", encoding="utf-8")
    assert _git(repo, "add", "README.md").returncode == 0
    assert _git(repo, "commit", "-m", "feat: branch change").returncode == 0
    assert _git(repo, "checkout", "wcq").returncode == 0

    fake_worktree = tmp_path / "not-a-worktree"
    fake_worktree.mkdir()

    result = _run(
        [
            "bash",
            str(script),
            "--branch",
            "feat/20260407-demo",
            "--base-sha",
            base_sha,
            "--worktree",
            str(fake_worktree),
        ],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "does not point to a git worktree" in result.stderr


def test_ff_merge_to_wcq_fast_forwards_and_cleans_up(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("ff_merge_to_wcq.sh")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    feature_worktree = repo / ".worktrees" / "feat-20260407-demo"

    add_worktree = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "feat/20260407-demo",
        str(feature_worktree),
        "wcq",
    )
    assert add_worktree.returncode == 0, add_worktree.stderr

    _write_executable(
        feature_worktree
        / ".agents"
        / "skills"
        / "auto-dev-workflow"
        / "scripts"
        / "run_final_gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    (feature_worktree / "README.md").write_text("feature branch\n", encoding="utf-8")
    assert _git(feature_worktree, "add", "README.md", ".agents").returncode == 0
    commit_result = _git(feature_worktree, "commit", "-m", "feat: branch change")
    assert commit_result.returncode == 0, commit_result.stderr
    feature_head = _git(feature_worktree, "rev-parse", "HEAD")
    assert feature_head.returncode == 0, feature_head.stderr

    result = _run(
        [
            "bash",
            str(script),
            "--branch",
            "feat/20260407-demo",
            "--base-sha",
            base_sha,
            "--worktree",
            str(feature_worktree),
        ],
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr
    assert not feature_worktree.exists()
    deleted_branch = _git(repo, "show-ref", "--verify", "refs/heads/feat/20260407-demo")
    assert deleted_branch.returncode != 0

    head_sha = _git(repo, "rev-parse", "HEAD")
    assert head_sha.returncode == 0, head_sha.stderr
    assert head_sha.stdout.strip() == feature_head.stdout.strip()

    head_message = _git(repo, "log", "-1", "--pretty=%s")
    assert head_message.returncode == 0, head_message.stderr
    assert head_message.stdout.strip() == "feat: branch change"


def test_ff_merge_to_wcq_refuses_branch_moving_during_final_gate(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("ff_merge_to_wcq.sh")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    feature_worktree = repo / ".worktrees" / "feat-20260407-moving-tip"

    add_worktree = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "feat/20260407-moving-tip",
        str(feature_worktree),
        "wcq",
    )
    assert add_worktree.returncode == 0, add_worktree.stderr

    _write_executable(
        feature_worktree
        / ".agents"
        / "skills"
        / "auto-dev-workflow"
        / "scripts"
        / "run_final_gate.sh",
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"feature_worktree={str(feature_worktree)!r}\n"
            "printf 'post gate move\\n' > \"$feature_worktree/post_gate.txt\"\n"
            'git -C "$feature_worktree" add post_gate.txt\n'
            "git -C \"$feature_worktree\" commit -m 'feat: branch moved during gate' >/dev/null\n"
        ),
    )
    (feature_worktree / "README.md").write_text("feature branch\n", encoding="utf-8")
    assert _git(feature_worktree, "add", "README.md", ".agents").returncode == 0
    commit_result = _git(feature_worktree, "commit", "-m", "feat: branch change")
    assert commit_result.returncode == 0, commit_result.stderr
    verified_head = _git(feature_worktree, "rev-parse", "HEAD")
    assert verified_head.returncode == 0, verified_head.stderr

    result = _run(
        [
            "bash",
            str(script),
            "--branch",
            "feat/20260407-moving-tip",
            "--base-sha",
            base_sha,
            "--worktree",
            str(feature_worktree),
        ],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "moved during final gate" in result.stderr
    assert feature_worktree.exists()
    assert _git(repo, "show-ref", "--verify", "refs/heads/feat/20260407-moving-tip").returncode == 0
    head_sha = _git(repo, "rev-parse", "HEAD")
    assert head_sha.returncode == 0, head_sha.stderr
    assert head_sha.stdout.strip() == base_sha


def test_ff_merge_to_wcq_refuses_non_fast_forward_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("ff_merge_to_wcq.sh")

    (repo / "README.md").write_text("wcq base change\n", encoding="utf-8")
    assert _git(repo, "add", "README.md").returncode == 0
    base_commit = _git(repo, "commit", "-m", "chore: update wcq base")
    assert base_commit.returncode == 0, base_commit.stderr
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    feature_worktree = repo / ".worktrees" / "feat-20260407-diverged"
    add_worktree = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "feat/20260407-diverged",
        str(feature_worktree),
        "HEAD~1",
    )
    assert add_worktree.returncode == 0, add_worktree.stderr
    _write_executable(
        feature_worktree
        / ".agents"
        / "skills"
        / "auto-dev-workflow"
        / "scripts"
        / "run_final_gate.sh",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    (feature_worktree / "README.md").write_text("feature branch change\n", encoding="utf-8")
    assert _git(feature_worktree, "add", "README.md", ".agents").returncode == 0
    commit_result = _git(feature_worktree, "commit", "-m", "feat: branch conflict change")
    assert commit_result.returncode == 0, commit_result.stderr

    result = _run(
        [
            "bash",
            str(script),
            "--branch",
            "feat/20260407-diverged",
            "--base-sha",
            base_sha,
            "--worktree",
            str(feature_worktree),
        ],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Cannot fast-forward wcq to 'feat/20260407-diverged'" in result.stderr
    assert feature_worktree.exists()
    assert _git(repo, "show-ref", "--verify", "refs/heads/feat/20260407-diverged").returncode == 0


def test_squash_merge_to_wcq_redirects_to_ff_merge_script(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = _script_path("squash_merge_to_wcq.sh")

    result = _run(
        ["bash", str(script)],
        cwd=repo,
    )

    assert result.returncode != 0
    assert "Use ff_merge_to_wcq.sh instead." in result.stderr
