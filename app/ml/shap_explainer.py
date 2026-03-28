from __future__ import annotations

import warnings
from typing import Dict, List, TypedDict

import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier


class ShapFeatureImpact(TypedDict):
    """Single feature impact entry used in SHAP summaries."""

    feature: str
    value: float
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
    for name, val, sv in zip(feature_names, feature_values, contrib):
        impacts.append(
            ShapFeatureImpact(
                feature=name,
                value=float(val),
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
    metrics: Dict[str, float | str],
    shap_summary: ShapSummary,
) -> str:
    """Render a human-readable Chinese Markdown report for the latest sample.

    The report is designed for consumption by higher-level Agents (Quant/CIO)
    and humans. It intentionally stays concise while still exposing the key
    model diagnostics:

    - predicted next-day up-move probability;
    - simple hold-out metrics (accuracy and AUC); and
    - the top positive and negative SHAP drivers.

    Args:
        ticker: Asset symbol (for example, ``\"BTC-USD\"`` or ``\"NVDA\"``).
        prob_up: Model-estimated probability that the next day's return is
            positive.
        metrics: Dictionary returned by :func:`train_lightgbm`, expected to
            include at least ``accuracy`` and ``auc``.
        shap_summary: Structured SHAP explanation from
            :func:`explain_latest_sample`.

    Returns:
        A Markdown string written in Chinese that explains the model's view on
        the most recent market state for the given asset.
    """

    probability_pct = prob_up * 100.0
    acc = metrics.get("mean_accuracy", metrics.get("accuracy"))
    auc = metrics.get("mean_auc", metrics.get("auc"))
    acc_str = f"{acc:.3f}" if isinstance(acc, (float, int)) else "N/A"
    auc_str = f"{auc:.3f}" if isinstance(auc, (float, int)) else "N/A"
    validation_note = (
        "5-fold TimeSeriesSplit"
        if "TimeSeriesSplit" in str(metrics.get("train_test_split", ""))
        else "Hold-out"
    )

    pos_lines: List[str] = []
    for imp in shap_summary.get("top_positive", []) or []:
        pos_lines.append(
            f"- **{imp['feature']}** 当前值约为 `{imp['value']:.4f}`，"
            f"对预测方向提供正向贡献 (SHAP ≈ +{abs(imp['shap']):.4f})。"
        )

    neg_lines: List[str] = []
    for imp in shap_summary.get("top_negative", []) or []:
        neg_lines.append(
            f"- **{imp['feature']}** 当前值约为 `{imp['value']:.4f}`，"
            f"对预测方向形成压制 (SHAP ≈ -{abs(imp['shap']):.4f})。"
        )

    positive_block = "\n".join(pos_lines) if pos_lines else "- 暂无显著正向驱动特征。"
    negative_block = "\n".join(neg_lines) if neg_lines else "- 暂无显著压制特征。"

    lines: List[str] = []
    lines.append(f"【LightGBM 量化预测报告】标的：`{ticker.upper()}`")
    lines.append("")
    lines.append(
        f"- **模型结论**：在最新可用数据下，模型估计 **下一交易日上涨概率约为 {probability_pct:.1f}%**。"
    )
    lines.append(
        f"- **历史表现（{validation_note}）**：平均 Accuracy ≈ {acc_str}，AUC ≈ {auc_str} "
        "(仅供参考，不构成收益承诺)。"
    )
    lines.append("")
    lines.append("### 核心看多驱动力（Top 正向特征）")
    lines.append("")
    lines.append(positive_block)
    lines.append("")
    lines.append("### 核心风险与压制因素（Top 负向特征）")
    lines.append("")
    lines.append(negative_block)

    return "\n".join(lines)
