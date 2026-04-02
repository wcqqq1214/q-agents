from __future__ import annotations

import warnings
from typing import Any, Dict, List, TypedDict

import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier

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
    *,
    target_label: str = "下一交易日上涨",
    model_label: str = "LightGBM",
) -> str:
    """Render a human-readable Chinese Markdown report for the latest sample.

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
        A Markdown string written in Chinese that explains the model's view on
        the most recent market state for the given asset.
    """

    probability_pct = prob_up * 100.0
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
            f"- **{imp['feature']}** 当前值约为 `{_format_feature_value(imp['value'])}`，"
            f"对预测方向提供正向贡献 (SHAP ≈ +{abs(imp['shap']):.4f})。"
        )

    neg_lines: List[str] = []
    for imp in shap_summary.get("top_negative", []) or []:
        neg_lines.append(
            f"- **{imp['feature']}** 当前值约为 `{_format_feature_value(imp['value'])}`，"
            f"对预测方向形成压制 (SHAP ≈ -{abs(imp['shap']):.4f})。"
        )

    positive_block = "\n".join(pos_lines) if pos_lines else "- 暂无显著正向驱动特征。"
    negative_block = "\n".join(neg_lines) if neg_lines else "- 暂无显著压制特征。"

    lines: List[str] = []
    lines.append(f"【{model_label} 量化预测报告】标的：`{ticker.upper()}`")
    lines.append("")
    lines.append(
        f"- **模型结论**：在最新可用数据下，模型估计 **{target_label} 的概率约为 {probability_pct:.1f}%**。"
    )
    lines.append(
        f"- **历史表现（{validation_note}）**：平均 Accuracy ≈ {acc_str}，AUC ≈ {auc_str} "
        "(仅供参考，不构成收益承诺)。"
    )
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
            sample_note = f"，验证样本数约 {int(requested_symbol_eval_rows)} 条"
        lines.append(
            f"- **单票外样本表现**：`{requested_symbol}` 的 OOS AUC ≈ {ticker_auc_str}，"
            f"Accuracy ≈ {ticker_acc_str}{sample_note}。"
        )
    elif metrics.get("requested_symbol_auc_unavailable"):
        lines.append(
            f"- **单票外样本表现**：`{requested_symbol}` 在当前验证窗口中标签过于单边，OOS AUC 暂不可用。"
        )
    lines.append("")
    lines.append("### 核心看多驱动力（Top 正向特征）")
    lines.append("")
    lines.append(positive_block)
    lines.append("")
    lines.append("### 核心风险与压制因素（Top 负向特征）")
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
        lines.append("### 历史相似阶段")
        lines.append("")
        lines.append(
            f"- 系统检索到 **{historical_similarity.get('n_matches', 0)} 个** 高相似历史窗口，"
            f"平均相似度约 **{avg_sim:.1f}%**。"
        )
        if same_symbol_matches or peer_group_matches or market_matches:
            lines.append(
                f"- 匹配策略采用 **同股票优先、peer group 次优先、全市场兜底**："
                f"同股票样本 {same_symbol_matches} 个，"
                f"peer group 样本 {peer_group_matches} 个，"
                f"全市场补充样本 {market_matches} 个。"
            )
        lines.append(
            f"- 这些相似阶段在随后 {historical_similarity.get('horizon_days', 3)} 个交易日的"
            f"平均收益约为 **{avg_ret:+.2f}%**，"
            f"正收益占比约 **{positive_rate:.1f}%**，"
            f"上涨异动命中率约 **{hit_rate:.1f}%**。"
        )

        top_matches = historical_similarity.get("matches", [])[:3]
        if top_matches:
            lines.append("")
            for match in top_matches:
                ret_pct = float(match.get("future_return_3d", 0.0)) * 100.0
                scope_label = {
                    "same_symbol": "同股票",
                    "peer_group": "peer group",
                    "market": "全市场",
                }.get(str(match.get("scope", "market")), "全市场")
                lines.append(
                    f"- `{match.get('symbol', '')}` 在 `{match.get('start_date', '')} ~ {match.get('end_date', '')}`"
                    f" 的窗口与当前最接近"
                    f"（{scope_label}）"
                    f"，相似度 **{float(match.get('similarity', 0.0)) * 100.0:.1f}%**，"
                    f"随后 3 日收益 **{ret_pct:+.2f}%**。"
                )

    return "\n".join(lines)
