"""Run context helpers for per-run report bundling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class RunContext:
    """Represents a single analysis run's output directory context."""

    run_id: str
    run_dir: Path
    asset: str


def _now_compact_utc8() -> str:
    tz = timezone(timedelta(hours=8))
    return (
        datetime.now(timezone.utc).astimezone(tz).replace(microsecond=0).strftime("%Y%m%d_%H%M%S")
    )


def _sanitize_asset(asset: str) -> str:
    a = (asset or "").strip().upper()
    a = re.sub(r"[^A-Z0-9\-_.]+", "_", a)
    return a or "UNKNOWN"


def make_run_dir(asset: str) -> RunContext:
    """Create `data/reports/{timestamp}_{asset}/` and return the run context."""

    asset_norm = _sanitize_asset(asset)
    run_id = _now_compact_utc8()
    run_dir = Path("data/reports") / f"{run_id}_{asset_norm}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(run_id=run_id, run_dir=run_dir, asset=asset_norm)
