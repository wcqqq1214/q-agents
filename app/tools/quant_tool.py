from __future__ import annotations

import logging
from typing import Any, Dict, TypedDict, cast

from langchain_core.tools import tool

from app.ml.feature_engine import build_dataset, load_ohlcv_with_macro
from app.ml.model_trainer import predict_proba_latest, train_lightgbm
from app.ml.shap_explainer import (
    ShapSummary,
    build_markdown_report,
    explain_latest_sample,
)

logger = logging.getLogger(__name__)


class MlQuantResult(TypedDict, total=False):
    """Typed dictionary representing the ML quant sub-report.

    This structure is designed to be directly serializable into the
    ``ml_quant`` field of ``quant.json`` as documented in ``ml_quant.md``.

    Attributes:
        model: Short identifier for the underlying model family (for example,
            ``\"lightgbm\"``).
        target: Name of the prediction target (e.g. ``\"next_3d_direction_filtered\"``
            for 3-day smoothed direction with threshold filter).
        data_source: Identifier of the market data source. For the current
            implementation this is ``\"yfinance_direct\"`` to distinguish it
            from any MCP-based fetchers.
        prob_up: Estimated probability that the next trading day's close is
            higher than today's close.
        prediction: Discrete direction label derived from ``prob_up``, one of
            ``\"up\"`` or ``\"down\"``.
        metrics: Dictionary with basic hold-out evaluation metrics such as
            accuracy and AUC.
        shap_insights: Compact SHAP summary as returned by
            :func:`explain_latest_sample`, containing top positive and
            negative feature contributions.
        markdown_report: Human-readable Chinese Markdown report summarizing
            the model's view on the latest market state.
        error: Optional human-readable error message if the pipeline failed
            before producing a meaningful prediction.
    """

    model: str
    target: str
    data_source: str
    prob_up: float
    prediction: str
    metrics: Dict[str, Any]
    shap_insights: ShapSummary
    markdown_report: str
    error: str


def _run_ml_quant_analysis_impl(ticker: str) -> MlQuantResult:
    """Internal implementation for the ML quant analysis pipeline.

    This function is separated from the LangChain tool wrapper so that it can
    be called both from tools (for agent use) and from the reporting pipeline
    (for scheduled batch runs) without duplication.
    """

    normalized = (ticker or "").strip().upper()
    base: MlQuantResult = MlQuantResult(
        model="lightgbm",
        target="next_3d_direction_filtered",
        data_source="yfinance_direct",
    )

    if not normalized:
        msg = "ticker is empty; cannot run ML quant analysis."
        logger.warning("run_ml_quant_analysis: %s", msg)
        base["error"] = msg
        return base

    try:
        df = load_ohlcv_with_macro(normalized, period_years=5)
        X, y = build_dataset(df)
        model, metrics = train_lightgbm(X, y)
        prob_up = predict_proba_latest(model, X)
        shap_summary = explain_latest_sample(model, X)
        markdown = build_markdown_report(
            ticker=normalized,
            prob_up=prob_up,
            metrics=metrics,
            shap_summary=shap_summary,
        )
    except Exception as exc:
        msg = (
            "ML quant pipeline failed; this usually indicates insufficient "
            "history, data quality issues, or an internal error. "
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning("run_ml_quant_analysis failed for %s: %s", normalized, msg, exc_info=True)
        base["error"] = msg
        return base

    prediction = "up" if prob_up >= 0.5 else "down"

    base["prob_up"] = float(prob_up)
    base["prediction"] = prediction
    base["metrics"] = cast(Dict[str, Any], metrics)
    base["shap_insights"] = shap_summary
    base["markdown_report"] = markdown
    return base


@tool("run_ml_quant_analysis")
def run_ml_quant_analysis(ticker: str) -> MlQuantResult:
    """Run a LightGBM + SHAP based 3-day smoothed direction analysis for a single asset.

    This tool is designed for Quant Agents that need a **compact but
    explainable** machine-learning view of an asset's short-term technical
    outlook. Given a ticker (such as ``\"AAPL\"`` or ``\"BTC-USD\"``), it:

    1. Fetches daily OHLCV for the main ticker plus DXY and VIX from Yahoo
       Finance, merges by date, and builds technical + macro features.
    2. Builds a thresholded 3-day smoothed direction label (R_future vs epsilon)
       and drops oscillation samples.
    3. Trains ``LGBMClassifier`` with strong regularization using
       ``TimeSeriesSplit(n_splits=5)`` and reports out-of-sample mean AUC/accuracy.
    4. Uses SHAP to attribute the **most recent day** prediction to top
       positive and negative features.
    5. Generates a Chinese Markdown summary with model conclusion and SHAP drivers.

    Typical usage:

    - When a user asks for a probability-style technical view such as
      \"How likely is BTC-USD to rise tomorrow based on recent price action?\"
    - When a Quant Agent is preparing a structured ``quant.json`` report and
      needs to populate the ``ml_quant`` sub-field for CIO consumption.

    Args:
        ticker: Asset symbol understood by Yahoo Finance (for example,
            ``\"NVDA\"``, ``\"AAPL\"``, ``\"BTC-USD\"``, ``\"DOGE-USD\"``). The
            symbol is internally uppercased; both US equities and major
            crypto pairs are supported as long as Yahoo provides sufficient
            history.

    Returns:
        An ``MlQuantResult`` dictionary that can be serialized directly into
        ``quant.json.ml_quant``. On success it includes keys:

        - ``model``: Currently ``\"lightgbm\"``.
        - ``target``: e.g. ``\"next_3d_direction_filtered\"``.
        - ``data_source``: ``\"yfinance_direct\"`` to distinguish from
          MCP-based sources.
        - ``prob_up``: Next-day up-move probability in ``[0, 1]``.
        - ``prediction``: ``\"up\"`` if ``prob_up >= 0.5`` else ``\"down\"``.
        - ``metrics``: Dictionary with ``mean_auc``, ``mean_accuracy``,
          ``fold_aucs``, ``train_test_split`` (e.g. TimeSeriesSplit_n5), and
          backward-compatible ``accuracy``/``auc``.
        - ``shap_insights``: Structured SHAP summary with top positive and
          negative features.
        - ``markdown_report``: Chinese Markdown explanation suitable for
          direct inclusion in human-facing or agent-facing reports.

        If an error occurs (for example, insufficient history or network
        issues when calling yfinance), the return value still contains
        ``model``, ``target`` and ``data_source`` along with an ``error``
        field describing the problem. Callers should check for the presence
        of ``error`` before trusting the numeric outputs.
    """

    return _run_ml_quant_analysis_impl(ticker)
