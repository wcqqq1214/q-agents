from __future__ import annotations

import logging
from typing import Any, Dict, TypedDict, cast

from langchain_core.tools import tool

from app.ml.features import PANEL_FEATURE_COLS, TEXT_BLOB_COL, build_panel_features
from app.ml.signal_filter import SignalFilterSummary, apply_similarity_signal_filter
from app.ml.model_trainer import predict_proba_latest, train_lightgbm_panel_with_text
from app.ml.shap_explainer import (
    ShapSummary,
    build_markdown_report,
    explain_latest_sample,
)
from app.ml.similarity import (
    HistoricalSimilaritySummary,
    find_similar_historical_periods,
)
from app.ml.text_features import transform_text_svd_features

logger = logging.getLogger(__name__)

PANEL_TARGET_COL = "target_up_big_move_t3"
PANEL_TARGET_NAME = "future_3d_up_big_move_gt_2pct_panel"
PANEL_TARGET_LABEL = "未来 3 个交易日出现超过 2% 的上涨异动"


class MlQuantResult(TypedDict, total=False):
    """Typed dictionary representing the ML quant sub-report.

    This structure is designed to be directly serializable into the
    ``ml_quant`` field of ``quant.json`` as documented in ``ml_quant.md``.

    Attributes:
        model: Short identifier for the underlying model family (for example,
            ``\"lightgbm\"``).
        target: Name of the prediction target.
        data_source: Identifier of the market data source. For the current
            implementation this is ``\"sqlite_panel_db\"``.
        prob_up: Estimated probability that the configured upside-event target
            occurs.
        prediction: Discrete label derived from ``prob_up``.
        final_prob_up: Probability after the similarity-confirmation filter.
        final_prediction: Final discrete label after the similarity filter.
        signal_filter: Compact description of whether historical similarity
            confirmed or contradicted the raw model direction.
        metrics: Dictionary with basic hold-out evaluation metrics such as
            accuracy and AUC.
        shap_insights: Compact SHAP summary as returned by
            :func:`explain_latest_sample`, containing top positive and
            negative feature contributions.
        markdown_report: Human-readable Chinese Markdown report summarizing
            the model's view on the latest market state.
        historical_similarity: Historical analog summary derived from panel
            feature cosine similarity search over recent windows.
        error: Optional human-readable error message if the pipeline failed
            before producing a meaningful prediction.
    """

    model: str
    target: str
    data_source: str
    prob_up: float
    prediction: str
    final_prob_up: float
    final_prediction: str
    signal_filter: SignalFilterSummary
    metrics: Dict[str, Any]
    shap_insights: ShapSummary
    markdown_report: str
    historical_similarity: HistoricalSimilaritySummary
    error: str


def _run_ml_quant_analysis_impl(ticker: str) -> MlQuantResult:
    """Internal implementation for the ML quant analysis pipeline.

    This function is separated from the LangChain tool wrapper so that it can
    be called both from tools (for agent use) and from the reporting pipeline
    (for scheduled batch runs) without duplication.
    """

    normalized = (ticker or "").strip().upper()
    base: MlQuantResult = MlQuantResult(
        model="lightgbm_panel",
        target=PANEL_TARGET_NAME,
        data_source="sqlite_panel_db",
    )

    if not normalized:
        msg = "ticker is empty; cannot run ML quant analysis."
        logger.warning("run_ml_quant_analysis: %s", msg)
        base["error"] = msg
        return base

    try:
        panel = build_panel_features()
        if panel.empty:
            raise ValueError("Panel dataset is empty. Build OHLC/news features first.")

        available_symbols = sorted(panel["symbol"].astype(str).unique().tolist())
        if normalized not in available_symbols:
            raise ValueError(
                f"Ticker {normalized!r} is not available in panel universe: {available_symbols}"
            )

        train_df = panel.dropna(subset=[PANEL_TARGET_COL]).copy()
        if train_df.empty:
            raise ValueError(f"No labeled training rows available for target {PANEL_TARGET_COL!r}.")

        X_train = train_df[PANEL_FEATURE_COLS]
        y_train = train_df[PANEL_TARGET_COL].astype(int)
        trade_dates = train_df["trade_date"]
        model, metrics, text_artifacts, train_feature_matrix = train_lightgbm_panel_with_text(
            X_train,
            y_train,
            trade_dates,
            train_df[TEXT_BLOB_COL],
            categorical_features=["symbol"],
        )

        latest_rows = panel.loc[panel["symbol"] == normalized].sort_values("trade_date")
        if latest_rows.empty:
            raise ValueError(f"No feature rows available for {normalized!r}.")

        latest_feature_rows = latest_rows[PANEL_FEATURE_COLS].reset_index(drop=True)
        latest_text_features = transform_text_svd_features(latest_rows[TEXT_BLOB_COL], text_artifacts)
        latest_feature_rows = latest_feature_rows.join(latest_text_features.reset_index(drop=True))
        latest_X = latest_feature_rows.tail(1)
        prob_up = predict_proba_latest(model, latest_X)
        shap_summary = explain_latest_sample(model, latest_X)

        similarity_history = (
            train_df[["symbol", "trade_date", "close", PANEL_TARGET_COL]]
            .reset_index(drop=True)
            .join(train_feature_matrix.drop(columns=["symbol"], errors="ignore").reset_index(drop=True))
        )
        similarity_query = (
            latest_rows[["symbol", "trade_date", "close"]]
            .reset_index(drop=True)
            .join(latest_feature_rows.drop(columns=["symbol"], errors="ignore").reset_index(drop=True))
        )
        historical_similarity = find_similar_historical_periods(
            similarity_history,
            similarity_query,
            target_col=PANEL_TARGET_COL,
        )
        signal_filter = apply_similarity_signal_filter(prob_up, historical_similarity)

        metrics = cast(Dict[str, Any], dict(metrics))
        metrics["n_symbols"] = int(train_df["symbol"].nunique())
        metrics["text_features"] = metrics.get("text_svd_components", 0)
        metrics["requested_symbol"] = normalized
        per_ticker_auc = metrics.get("per_ticker_auc", {})
        if isinstance(per_ticker_auc, dict) and normalized in per_ticker_auc:
            metrics["requested_symbol_auc"] = float(per_ticker_auc[normalized])
        per_ticker_accuracy = metrics.get("per_ticker_accuracy", {})
        if isinstance(per_ticker_accuracy, dict) and normalized in per_ticker_accuracy:
            metrics["requested_symbol_accuracy"] = float(per_ticker_accuracy[normalized])
        per_ticker_eval_rows = metrics.get("per_ticker_eval_rows", {})
        if isinstance(per_ticker_eval_rows, dict) and normalized in per_ticker_eval_rows:
            metrics["requested_symbol_eval_rows"] = int(per_ticker_eval_rows[normalized])
        per_ticker_auc_unavailable = metrics.get("per_ticker_auc_unavailable", [])
        if isinstance(per_ticker_auc_unavailable, list):
            metrics["requested_symbol_auc_unavailable"] = normalized in {
                str(item).strip().upper() for item in per_ticker_auc_unavailable
            }
        markdown = build_markdown_report(
            ticker=normalized,
            prob_up=prob_up,
            metrics=metrics,
            shap_summary=shap_summary,
            historical_similarity=historical_similarity,
            signal_filter=signal_filter,
            target_label=PANEL_TARGET_LABEL,
            model_label="LightGBM Panel",
        )
    except Exception as exc:
        msg = (
            "ML quant pipeline failed; this usually indicates insufficient "
            "database coverage, data quality issues, or an internal error. "
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning("run_ml_quant_analysis failed for %s: %s", normalized, msg, exc_info=True)
        base["error"] = msg
        return base

    prediction = "up_big_move" if prob_up >= 0.5 else "no_up_big_move"
    final_prob_up = float(signal_filter["adjusted_probability"])
    final_prediction = "up_big_move" if final_prob_up >= 0.5 else "no_up_big_move"

    base["prob_up"] = float(prob_up)
    base["prediction"] = prediction
    base["final_prob_up"] = final_prob_up
    base["final_prediction"] = final_prediction
    base["signal_filter"] = signal_filter
    base["metrics"] = cast(Dict[str, Any], metrics)
    base["shap_insights"] = shap_summary
    base["historical_similarity"] = historical_similarity
    base["markdown_report"] = markdown
    base["feature_count"] = int(train_feature_matrix.shape[1])
    return base


@tool("run_ml_quant_analysis")
def run_ml_quant_analysis(ticker: str) -> MlQuantResult:
    """Run a panel LightGBM + SHAP analysis for a single asset.

    This tool is designed for Quant Agents that need a **compact but
    explainable** machine-learning view of an asset's short-term technical
    outlook. Given a ticker (such as ``\"AAPL\"`` or ``\"NVDA\"``), it:

    1. Loads the local OHLC + news-sentiment dataset for the stock universe and
       builds one unified panel dataset.
    2. Uses the event-style target ``future_3d_up_big_move_gt_2pct_panel`` to
       focus on actionable upside moves instead of noisy next-day drift.
    3. Trains ``LGBMClassifier`` with date-blocked panel CV so each trade date
       is fully assigned to train or test.
    4. Converts each day's aggregated news text into ``text_svd_*`` features
       via fold-isolated TF-IDF + SVD and fuses them with panel factors.
    5. Uses SHAP to attribute the **latest row for the requested ticker** to top
       positive and negative features.
    6. Retrieves historically similar panel windows via cosine similarity on
       recent feature averages, then summarizes their realized forward returns.
    7. Generates a Chinese Markdown summary with model conclusion, SHAP drivers,
       and historical analog evidence.

    Typical usage:

    - When a user asks for a probability-style technical view such as
      \"How likely is NVDA to make a meaningful upside move over the next few days?\"
    - When a Quant Agent is preparing a structured ``quant.json`` report and
      needs to populate the ``ml_quant`` sub-field for CIO consumption.

    Args:
        ticker: Asset symbol available in the local stock panel database (for
            example, ``\"NVDA\"`` or ``\"AAPL\"``). The symbol is internally
            uppercased.

    Returns:
        An ``MlQuantResult`` dictionary that can be serialized directly into
        ``quant.json.ml_quant``. On success it includes keys:

        - ``model``: Currently ``\"lightgbm_panel\"``.
        - ``target``: ``\"future_3d_up_big_move_gt_2pct_panel\"``.
        - ``data_source``: ``\"sqlite_panel_db\"``.
        - ``prob_up``: Probability that the ticker posts an upside move greater
          than 2% within the next 3 trading days.
        - ``prediction``: ``\"up_big_move\"`` if ``prob_up >= 0.5`` else
          ``\"no_up_big_move\"``.
        - ``final_prob_up``: Similarity-filtered probability used for the final
          trading signal.
        - ``final_prediction``: Final label after the similarity filter.
        - ``signal_filter``: Whether historical similarity confirmed or
          contradicted the raw model direction, plus a suggested position
          multiplier.
        - ``metrics``: Dictionary with ``mean_auc``, ``mean_accuracy``,
          ``fold_aucs``, ``train_test_split`` (e.g. PanelTimeSeriesSplit_n5), and
          backward-compatible ``accuracy``/``auc``.
        - ``shap_insights``: Structured SHAP summary with top positive and
          negative features.
        - ``historical_similarity``: Summary of the most similar historical
          panel windows, including average forward return and top matches.
        - ``markdown_report``: Chinese Markdown explanation suitable for
          direct inclusion in human-facing or agent-facing reports.

        If an error occurs (for example, insufficient local database coverage),
        the return value still contains
        ``model``, ``target`` and ``data_source`` along with an ``error``
        field describing the problem. Callers should check for the presence
        of ``error`` before trusting the numeric outputs.
    """

    return _run_ml_quant_analysis_impl(ticker)
