from __future__ import annotations

import warnings
from typing import Any, Dict, List, TypedDict

import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier

from app.ml.signal_filter import SignalFilterSummary, apply_similarity_signal_filter
from app.ml.similarity import HistoricalSimilaritySummary


class ShapFeatureImpact(TypedDict):
    """Single feature impact entry used in SHAP summaries."""

    feature: str
    value: float | str
    shap: float


class ShapSummary(TypedDict, total=False):
    """Structured SHAP explanation for the latest sample.

    Attributes:
        top_positive: List of features that contribute most positively toward
            the predicted class (sorted by descending SHAP value).
        top_negative: List of features that contribute most negatively toward
            the predicted class (sorted by ascending SHAP value).
    """

    top_positive: List[ShapFeatureImpact]
    top_negative: List[ShapFeatureImpact]


def _select_class_shap_values(
    shap_values: object,
) -> np.ndarray:
    """Normalize SHAP outputs to a 1D array for the positive class.

    For binary classification with tree-based models, ``shap.TreeExplainer``
    typically returns a list with two arrays (for class 0 and 1). This helper
    selects the positive-class contribution vector. If the explainer already
    returns a single 2D array, that array is used directly.
    """

    if isinstance(shap_values, list) and len(shap_values) >= 2:
        # Binary classification: pick the SHAP values for class 1.
        arr = np.asarray(shap_values[1])
    else:
        arr = np.asarray(shap_values)
    if arr.ndim == 2 and arr.shape[0] == 1:
        return arr[0]
    if arr.ndim == 1:
        return arr
    raise ValueError("Unexpected SHAP values shape; expected (1, n_features) or (n_features,).")


def _serialize_feature_value(value: Any) -> float | str:
    """Serialize a feature value for JSON/report output."""

    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    return str(value)


def _format_feature_value(value: float | str) -> str:
    """Render numeric and categorical feature values consistently."""

    if isinstance(value, float):
        return f"{value:.4f}"
    return value


def _probability_direction_label(probability: float) -> str:
    """Return a directional label for a probability around the 0.5 boundary."""

    if probability > 0.5:
        return "Bullish"
    if probability < 0.5:
        return "Bearish"
    return "Neutral"


def _ml_policy_label(policy: Any) -> str:
    """Return a human-readable label for the ML authority policy."""

    return {
        "primary_signal": "PRIMARY_SIGNAL (usable as a primary signal)",
        "auxiliary_only": "AUXILIARY_ONLY (supporting signal only)",
        "event_driven_only": "EVENT_DRIVEN_ONLY (ML directional signal disabled)",
    }.get(str(policy), "PRIMARY_SIGNAL (usable as a primary signal)")


def explain_latest_sample(
    model: LGBMClassifier,
    X: pd.DataFrame,
    top_pos: int = 3,
    top_neg: int = 2,
) -> ShapSummary:
    """Compute SHAP-based feature contributions for the latest sample.

    This function focuses exclusively on the **most recent row** in the
    feature matrix ``X``, as required by the project design. It returns a
    compact, sorted summary of the most supportive and most adverse features
    for the model's prediction on that sample.

    Args:
        model: Trained LightGBM classifier.
        X: Full feature matrix used for training, with the last row
            representing the most recent market state.
        top_pos: Maximum number of positively contributing features to
            return.
        top_neg: Maximum number of negatively contributing features to
            return.

    Returns:
        A ``ShapSummary`` dictionary containing ``top_positive`` and
        ``top_negative`` lists, where each element includes the feature name,
        its current value, and its SHAP contribution.
    """

    if X.empty:
        raise ValueError("Feature matrix X is empty; cannot compute SHAP values.")

    latest = X.iloc[[-1]]
    explainer = shap.TreeExplainer(model)
    # Suppress noisy UserWarnings from SHAP about return types; the code
    # below explicitly normalizes the output format.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            module=r"shap\.explainers\._tree",
        )
        raw_values = explainer.shap_values(latest)
    contrib = _select_class_shap_values(raw_values)

    if contrib.shape[0] != latest.shape[1]:
        raise ValueError("Mismatch between SHAP contribution length and feature dimension.")

    feature_names = list(latest.columns)
    feature_values = latest.iloc[0].tolist()

    impacts: List[ShapFeatureImpact] = []
    for name, val, sv in zip(feature_names, feature_values, contrib, strict=False):
        impacts.append(
            ShapFeatureImpact(
                feature=name,
                value=_serialize_feature_value(val),
                shap=float(sv),
            )
        )

    # Positive and negative contributions sorted separately.
    positives = sorted(
        (imp for imp in impacts if imp["shap"] > 0),
        key=lambda x: x["shap"],
        reverse=True,
    )
    negatives = sorted(
        (imp for imp in impacts if imp["shap"] < 0),
        key=lambda x: x["shap"],
    )

    summary: ShapSummary = ShapSummary(
        top_positive=positives[:top_pos],
        top_negative=negatives[:top_neg],
    )
    return summary


def build_markdown_report(
    ticker: str,
    prob_up: float,
    metrics: Dict[str, Any],
    shap_summary: ShapSummary,
    historical_similarity: HistoricalSimilaritySummary | None = None,
    signal_filter: SignalFilterSummary | None = None,
    *,
    target_label: str = "the next trading day closes higher",
    model_label: str = "LightGBM",
) -> str:
    """Render a human-readable English Markdown report for the latest sample.

    The report is designed for consumption by higher-level Agents (Quant/CIO)
    and humans. It intentionally stays concise while still exposing the key
    model diagnostics:

    - predicted target-event probability;
    - simple hold-out metrics (accuracy and AUC); and
    - the top positive and negative SHAP drivers.

    Args:
        ticker: Asset symbol (for example, ``\"BTC-USD\"`` or ``\"NVDA\"``).
        prob_up: Model-estimated probability that the target event is
            positive.
        metrics: Dictionary returned by :func:`train_lightgbm`, expected to
            include at least ``accuracy`` and ``auc``.
        shap_summary: Structured SHAP explanation from
            :func:`explain_latest_sample`.
        target_label: Human-readable target description shown in the report.
        model_label: Display name of the model shown in the report header.

    Returns:
        A Markdown string in English that explains the model's view on the
        most recent market state for the given asset.
    """

    probability_pct = prob_up * 100.0
    signal_filter = signal_filter or apply_similarity_signal_filter(
        prob_up,
        historical_similarity,
        requested_symbol_auc=metrics.get("requested_symbol_auc"),
        requested_symbol_auc_unavailable=bool(metrics.get("requested_symbol_auc_unavailable")),
    )
    final_prob_pct = float(signal_filter["adjusted_probability"]) * 100.0
    acc = metrics.get("mean_accuracy", metrics.get("accuracy"))
    auc = metrics.get("mean_auc", metrics.get("auc"))
    acc_str = f"{acc:.3f}" if isinstance(acc, (float, int)) else "N/A"
    auc_str = f"{auc:.3f}" if isinstance(auc, (float, int)) else "N/A"
    split_label = str(metrics.get("train_test_split", ""))
    if "PanelTimeSeriesSplit" in split_label:
        validation_note = "5-fold PanelTimeSeriesSplit"
    elif "TimeSeriesSplit" in split_label:
        validation_note = "5-fold TimeSeriesSplit"
    else:
        validation_note = "Hold-out"

    pos_lines: List[str] = []
    for imp in shap_summary.get("top_positive", []) or []:
        pos_lines.append(
            f"- **{imp['feature']}** currently reads approximately "
            f"`{_format_feature_value(imp['value'])}` and provides a positive "
            f"contribution to the forecast (SHAP ≈ +{abs(imp['shap']):.4f})."
        )

    neg_lines: List[str] = []
    for imp in shap_summary.get("top_negative", []) or []:
        neg_lines.append(
            f"- **{imp['feature']}** currently reads approximately "
            f"`{_format_feature_value(imp['value'])}` and acts as a headwind "
            f"for the forecast (SHAP ≈ -{abs(imp['shap']):.4f})."
        )

    positive_block = "\n".join(pos_lines) if pos_lines else "- No strong positive drivers identified."
    negative_block = "\n".join(neg_lines) if neg_lines else "- No strong negative drivers identified."

    lines: List[str] = []
    lines.append(f"# {model_label} Quant Prediction Report for `{ticker.upper()}`")
    lines.append("")
    lines.append(
        f"- **Model conclusion**: on the latest available data, the model "
        f"estimates the probability of **{target_label}** at approximately "
        f"**{probability_pct:.1f}%**."
    )
    lines.append(
        f"- **Historical validation ({validation_note})**: mean Accuracy ≈ "
        f"{acc_str}, AUC ≈ {auc_str} (reference only; not a return guarantee)."
    )
    alignment_label = {
        "confirmed": "Direction confirmed",
        "contradicted": "Direction contradicted",
        "neutral": "Direction neutral",
        "unavailable": "No similarity confirmation",
    }.get(signal_filter["alignment"], "No similarity confirmation")
    final_direction = _probability_direction_label(float(signal_filter["adjusted_probability"]))
    lines.append(
        f"- **Final trading signal**: after similarity filtering, the "
        f"probability is approximately {final_prob_pct:.1f}%, with a "
        f"**{final_direction}** direction; the current status is "
        f"**{alignment_label}**, with a suggested position multiplier of "
        f"**{float(signal_filter['position_multiplier']):.2f}x**."
    )
    ml_policy = signal_filter.get("ml_policy")
    if ml_policy == "event_driven_only":
        lines.append(
            f"- **ML signal authority**: {_ml_policy_label(ml_policy)}. The "
            "single-symbol OOS AUC is weak, so ML-led directionality is "
            "disabled and event/news/fundamental modules should take over."
        )
    elif ml_policy == "auxiliary_only":
        lines.append(
            f"- **ML signal authority**: {_ml_policy_label(ml_policy)}. The "
            "single-symbol OOS AUC only supports auxiliary usage, so the ML "
            "probability should not trigger a trade on its own."
        )
    else:
        lines.append(f"- **ML signal authority**: {_ml_policy_label(ml_policy)}.")
    requested_symbol = str(metrics.get("requested_symbol", ticker)).upper()
    requested_symbol_auc = metrics.get("requested_symbol_auc")
    requested_symbol_accuracy = metrics.get("requested_symbol_accuracy")
    requested_symbol_eval_rows = metrics.get("requested_symbol_eval_rows")
    if isinstance(requested_symbol_auc, (float, int)):
        ticker_auc_str = f"{float(requested_symbol_auc):.3f}"
        ticker_acc_str = (
            f"{float(requested_symbol_accuracy):.3f}"
            if isinstance(requested_symbol_accuracy, (float, int))
            else "N/A"
        )
        sample_note = ""
        if isinstance(requested_symbol_eval_rows, (float, int)):
            sample_note = f", evaluation sample size approximately {int(requested_symbol_eval_rows)}"
        lines.append(
            f"- **Single-symbol OOS performance**: `{requested_symbol}` has "
            f"OOS AUC ≈ {ticker_auc_str}, Accuracy ≈ {ticker_acc_str}{sample_note}."
        )
    elif metrics.get("requested_symbol_auc_unavailable"):
        lines.append(
            f"- **Single-symbol OOS performance**: `{requested_symbol}` has "
            "overly one-sided labels in the current validation window, so OOS "
            "AUC is unavailable."
        )
    lines.append("")
    lines.append("### Core Bullish Drivers (Top Positive Features)")
    lines.append("")
    lines.append(positive_block)
    lines.append("")
    lines.append("### Key Risks and Headwinds (Top Negative Features)")
    lines.append("")
    lines.append(negative_block)

    if historical_similarity and historical_similarity.get("n_matches", 0) > 0:
        avg_sim = float(historical_similarity.get("avg_similarity", 0.0)) * 100.0
        avg_ret = float(historical_similarity.get("avg_future_return_3d", 0.0)) * 100.0
        hit_rate = float(historical_similarity.get("target_hit_rate", 0.0)) * 100.0
        positive_rate = float(historical_similarity.get("positive_rate", 0.0)) * 100.0
        same_symbol_matches = int(historical_similarity.get("same_symbol_matches", 0))
        peer_group_matches = int(historical_similarity.get("peer_group_matches", 0))
        market_matches = int(historical_similarity.get("market_matches", 0))
        lines.append("")
        lines.append("### Historical Analog Windows")
        lines.append("")
        lines.append(
            f"- The system found **{historical_similarity.get('n_matches', 0)}** "
            f"high-similarity historical windows, with average similarity of "
            f"**{avg_sim:.1f}%**."
        )
        if same_symbol_matches or peer_group_matches or market_matches:
            lines.append(
                f"- Matching policy is **same symbol first, then peer group, "
                f"then market fallback**: {same_symbol_matches} same-symbol "
                f"matches, {peer_group_matches} peer-group matches, and "
                f"{market_matches} market matches."
            )
        lines.append(
            f"- Over the subsequent {historical_similarity.get('horizon_days', 3)} "
            f"trading days, these analog windows delivered an average return of "
            f"**{avg_ret:+.2f}%**, a positive-return rate of **{positive_rate:.1f}%**, "
            f"and a target-hit rate of **{hit_rate:.1f}%**."
        )

        top_matches = historical_similarity.get("matches", [])[:3]
        if top_matches:
            lines.append("")
            for match in top_matches:
                ret_pct = float(match.get("future_return_3d", 0.0)) * 100.0
                scope_label = {
                    "same_symbol": "same symbol",
                    "peer_group": "peer group",
                    "market": "market",
                }.get(str(match.get("scope", "market")), "market")
                lines.append(
                    f"- `{match.get('symbol', '')}` in the window "
                    f"`{match.get('start_date', '')} ~ {match.get('end_date', '')}` "
                    f"is one of the closest analogs ({scope_label}), with "
                    f"similarity **{float(match.get('similarity', 0.0)) * 100.0:.1f}%** "
                    f"and a subsequent 3-day return of **{ret_pct:+.2f}%**."
                )

    return "\n".join(lines)
