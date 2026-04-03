"""Tests for startup script orchestration."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_start_all_waits_for_mcp_bootstrap(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    startup_dir = tmp_path / "scripts" / "startup"
    startup_dir.mkdir(parents=True)

    source_script = repo_root / "scripts" / "startup" / "start_all.sh"
    target_script = startup_dir / "start_all.sh"
    target_script.write_text(source_script.read_text(encoding="utf-8"), encoding="utf-8")
    target_script.chmod(0o755)

    log_path = tmp_path / "events.log"
    quoted_log_path = str(log_path)

    _write_executable(
        startup_dir / "start_mcp_servers.sh",
        f"""#!/bin/bash
echo "mcp-start" >> "{quoted_log_path}"
/usr/bin/sleep 0.2
echo "mcp-end" >> "{quoted_log_path}"
""",
    )
    _write_executable(
        startup_dir / "start_api.sh",
        f"""#!/bin/bash
echo "api-start" >> "{quoted_log_path}"
/usr/bin/sleep 0.05
echo "api-end" >> "{quoted_log_path}"
""",
    )
    _write_executable(
        startup_dir / "start_frontend.sh",
        f"""#!/bin/bash
echo "frontend-start" >> "{quoted_log_path}"
/usr/bin/sleep 0.05
echo "frontend-end" >> "{quoted_log_path}"
""",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "lsof",
        """#!/bin/bash
exit 1
""",
    )
    _write_executable(
        bin_dir / "sleep",
        """#!/bin/bash
/usr/bin/sleep 0.01
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(target_script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    events = log_path.read_text(encoding="utf-8").splitlines()
    assert "mcp-end" in events
    assert "api-start" in events
    assert events.index("mcp-end") < events.index("api-start")
