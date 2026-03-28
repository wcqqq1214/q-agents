"""ML quant module report generator.

Exposes:
    generate_report(asset: str, run_dir: str) -> dict

This module produces a standalone JSON report for the LightGBM+SHAP-based
quantitative signal. It mirrors the style of the existing ``news`` and
``quant`` report generators so that downstream tooling can either read the
embedded ``ml_quant`` block inside ``quant.json`` or consume this dedicated
file directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, TypedDict, cast

from app.reporting.writer import write_json
from app.tools.quant_tool import run_ml_quant_analysis


class MlQuantBundle(TypedDict, total=False):
    """Top-level ML quant report bundle written to disk.

    Attributes:
        asset: Normalized asset symbol (e.g. ``NVDA``, ``BTC-USD``).
        module: Fixed string ``\"ml_quant\"`` identifying this report type.
        meta: Metadata including generation time and data source hint.
        ml_quant: The full result dictionary returned by
            :func:`run_ml_quant_analysis`.
        report_path: Filesystem path to the JSON report that was written.
    """

    asset: str
    module: str
    meta: Dict[str, Any]
    ml_quant: Dict[str, Any]
    report_path: str


def generate_report(asset: str, run_dir: str) -> MlQuantBundle:
    """Generate the ML quant report and persist it as `ml_quant.json`.

    This function is a thin wrapper around the LangChain tool
    :func:`run_ml_quant_analysis`. It is intended for use in scheduled batch
    jobs or pipelines where each analytical module writes its own JSON file
    into a per-run directory.

    Typical usage:

    - A reporting orchestrator iterates over a list of tickers and, for each
      one, calls:
        - :func:`app.quant.generate_report.generate_report` to produce
          ``quant.json``; and
        - :func:`generate_report` from this module to produce an additional
          ``ml_quant.json`` focused solely on the machine-learning signal.

    Args:
        asset: Asset symbol understood by Yahoo Finance (for example,
            ``\"NVDA\"``, ``\"AAPL\"``, ``\"BTC-USD\"``, ``\"DOGE-USD\"``).
            The symbol is uppercased internally.
        run_dir: Directory where the report JSON file should be written. The
            directory will be created if it does not already exist.

    Returns:
        An ``MlQuantBundle`` dictionary with keys:

        - ``asset``: Normalized symbol.
        - ``module``: Always ``\"ml_quant\"``.
        - ``meta``: Metadata including ``generated_at_utc``.
        - ``ml_quant``: Result from :func:`run_ml_quant_analysis`.
        - ``report_path``: Filesystem path to the written JSON file.
    """

    asset_norm = (asset or "").strip().upper()
    if not asset_norm:
        raise ValueError("asset is empty.")

    out_dir = Path(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Invoke the underlying tool; the result is already a structured dict.
    result = run_ml_quant_analysis.invoke({"ticker": asset_norm})
    ml_quant = cast(Dict[str, Any], result if isinstance(result, dict) else {})

    report: Dict[str, Any] = {
        "asset": asset_norm,
        "module": "ml_quant",
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
        "ml_quant": ml_quant,
    }

    path = out_dir / "ml_quant.json"
    write_json(path, report)
    report["report_path"] = str(path)
    return cast(MlQuantBundle, report)
