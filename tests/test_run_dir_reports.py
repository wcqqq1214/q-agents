from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.graph_multi import run_once


@pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="Integration test requires MINIMAX_API_KEY in environment/.env.",
)
def test_per_run_dir_contains_four_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Run inside a temp cwd so we don't pollute repo `reports/` during tests.
    monkeypatch.chdir(tmp_path)

    state = run_once("Please analyze BTC with quant/news/social and give a trading recommendation.")
    run_dir = state.get("run_dir")
    assert run_dir, "run_dir must be set in AgentState"

    out = Path(run_dir)
    assert out.exists() and out.is_dir()

    expected = ["quant.json", "news.json", "social.json", "cio.json"]
    for name in expected:
        p = out / name
        assert p.exists(), f"missing {name} in run_dir"
        obj = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(obj, dict)
        assert obj.get("asset")
        assert obj.get("module") in {"quant", "news", "social", "cio"}
        assert "meta" in obj and isinstance(obj["meta"], dict)

