"""Model registry for panel LightGBM orchestration.

Provides a unified interface for training, reporting, and formatting output
for the single supported model family: the panel LightGBM classifier.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Literal

import numpy as np
import pandas as pd

from app.ml.features import PANEL_FEATURE_COLS, TEXT_BLOB_COL, build_panel_features
from app.ml.model_trainer import (
    predict_proba_latest,
    train_lightgbm,
    train_lightgbm_panel_with_text,
)
from app.ml.similarity import HistoricalSimilaritySummary, find_similar_historical_periods
from app.ml.text_features import transform_text_svd_features

logger = logging.getLogger(__name__)

ModelType = Literal["lightgbm"]
DEFAULT_SYMBOL_TARGET_COL = "target_up_big_move_t3"
DEFAULT_LIGHTGBM_SCOPE = "panel"


def _is_finite_number(value: Any) -> bool:
    """Return whether value is a finite real number."""

    if not isinstance(value, (int, float, np.floating)):
        return False
    return math.isfinite(float(value))


def _format_float(value: Any, precision: int = 4) -> str:
    """Format finite numeric values, otherwise return N/A."""

    if not _is_finite_number(value):
        return "N/A"
    return f"{float(value):.{precision}f}"


def _format_percent_from_probability(value: Any) -> str:
    """Format a probability-like numeric value as a percentage string."""

    if not _is_finite_number(value):
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def _extract_requested_symbol_metrics(metrics: Dict[str, Any], symbol: str | None) -> Dict[str, Any]:
    """Return single-symbol OOS metrics derived from panel evaluation artifacts."""

    if not symbol:
        return {}

    symbol_norm = str(symbol).strip().upper()
    payload: Dict[str, Any] = {"requested_symbol": symbol_norm}

    per_ticker_auc = metrics.get("per_ticker_auc", {})
    if isinstance(per_ticker_auc, dict):
        symbol_auc = per_ticker_auc.get(symbol_norm)
        if _is_finite_number(symbol_auc):
            payload["requested_symbol_auc"] = float(symbol_auc)

    per_ticker_accuracy = metrics.get("per_ticker_accuracy", {})
    if isinstance(per_ticker_accuracy, dict):
        symbol_accuracy = per_ticker_accuracy.get(symbol_norm)
        if _is_finite_number(symbol_accuracy):
            payload["requested_symbol_accuracy"] = float(symbol_accuracy)

    per_ticker_eval_rows = metrics.get("per_ticker_eval_rows", {})
    if isinstance(per_ticker_eval_rows, dict):
        symbol_eval_rows = per_ticker_eval_rows.get(symbol_norm)
        if isinstance(symbol_eval_rows, (int, float, np.integer, np.floating)) and math.isfinite(float(symbol_eval_rows)):
            payload["requested_symbol_eval_rows"] = int(symbol_eval_rows)

    unavailable = metrics.get("per_ticker_auc_unavailable", [])
    if isinstance(unavailable, list):
        payload["requested_symbol_auc_unavailable"] = symbol_norm in {str(item).strip().upper() for item in unavailable}

    return payload


def _normalize_model_types(model_types: List[str] | None) -> List[ModelType]:
    """Validate supported model types.

    GRU/LSTM logic has been removed. Any non-LightGBM model request is rejected
    explicitly so callers fail loudly instead of silently receiving a partial
    result set.
    """

    if model_types is None:
        return ["lightgbm"]

    normalized = [str(model_type).strip().lower() for model_type in model_types if str(model_type).strip()]
    if not normalized:
        return ["lightgbm"]

    invalid = sorted({model_type for model_type in normalized if model_type != "lightgbm"})
    if invalid:
        raise ValueError(
            "Only 'lightgbm' is supported. GRU/LSTM logic has been removed. "
            f"Unsupported model types: {invalid}"
        )

    return ["lightgbm"]


def _extract_parameters(model: Any, model_type: str, _unused: Any = None) -> Dict[str, Any]:
    """Extract parameters from the supported model family."""

    if model_type != "lightgbm":
        raise ValueError(f"Unknown model type: {model_type}")
    return model.get_params()


def _calculate_fusion_score(predictions: Dict[str, float], metrics: Dict[str, Dict[str, float]]) -> float:
    """Return the aggregate score across available models.

    With the repository now standardized on a single LightGBM model, the
    fusion score is effectively the LightGBM prediction itself. The helper
    still accepts dictionaries so existing call sites remain simple.
    """

    finite_predictions = [float(pred) for pred in predictions.values() if _is_finite_number(pred)]
    if not finite_predictions:
        return float("nan")
    if len(finite_predictions) == 1:
        return finite_predictions[0]

    missing_models = [model_name for model_name in predictions if model_name not in metrics]
    if missing_models:
        logger.warning(
            "Missing metrics for models %s. Falling back to simple mean.",
            missing_models,
        )
        return float(np.mean(finite_predictions))

    weighted_pairs = [
        (float(predictions[model_name]), float(metrics[model_name]["mean_auc"]))
        for model_name in predictions
        if _is_finite_number(predictions[model_name]) and _is_finite_number(metrics[model_name].get("mean_auc"))
    ]
    if not weighted_pairs:
        return float(np.mean(finite_predictions))

    total_auc = sum(auc for _, auc in weighted_pairs)
    if total_auc <= 0:
        return float(np.mean(finite_predictions))

    return float(sum(pred * auc / total_auc for pred, auc in weighted_pairs))


def _extract_feature_importance(model: Any, X: pd.DataFrame, top_k: int = 3) -> List[Dict[str, Any]]:
    """Extract top K feature importances from LightGBM model."""

    try:
        importances = model.feature_importances_
        feature_names = X.columns.tolist()

        if len(feature_names) == 0 or len(importances) == 0:
            logger.warning("Empty feature names or importances")
            return []
        if len(importances) != len(feature_names):
            logger.warning(
                "Feature count mismatch: %s importances vs %s names",
                len(importances),
                len(feature_names),
            )
            return []

        top_k = min(top_k, len(importances))
        top_indices = np.argsort(importances)[-top_k:][::-1]
        return [
            {
                "name": str(feature_names[idx]),
                "importance": float(importances[idx]),
            }
            for idx in top_indices
        ]
    except Exception as exc:
        logger.error("Failed to extract feature importance: %s", exc)
        return []


def _load_panel_lightgbm_dataset(
    symbol: str,
    target_col: str = DEFAULT_SYMBOL_TARGET_COL,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.DataFrame]:
    """Load the unified panel dataset and latest inference rows for one symbol."""

    panel = build_panel_features(start_date=start_date, end_date=end_date)
    if panel.empty:
        raise ValueError("Panel feature dataset is empty")

    available_symbols = sorted(panel["symbol"].astype(str).unique().tolist())
    if symbol not in available_symbols:
        raise ValueError(f"Symbol {symbol!r} not found in panel universe: {available_symbols}")

    train_df = panel.dropna(subset=[target_col]).copy()
    if train_df.empty:
        raise ValueError(f"No labeled panel rows available for target {target_col}")

    X = train_df[PANEL_FEATURE_COLS]
    y = train_df[target_col].astype(int)
    trade_dates = train_df["trade_date"]
    train_text = train_df[TEXT_BLOB_COL]

    latest_symbol_rows = panel.loc[panel["symbol"].astype(str) == symbol].sort_values("trade_date")
    if latest_symbol_rows.empty:
        raise ValueError(f"No panel feature rows available for {symbol}")

    return train_df, X, y, trade_dates, train_text, latest_symbol_rows


def _build_historical_similarity_summary(
    train_df: pd.DataFrame,
    train_feature_matrix: pd.DataFrame,
    symbol_rows: pd.DataFrame,
    symbol_feature_matrix: pd.DataFrame,
    *,
    target_col: str = DEFAULT_SYMBOL_TARGET_COL,
) -> HistoricalSimilaritySummary | None:
    """Build a historical analog summary for the latest symbol window."""

    required_base_cols = {"symbol", "trade_date", "close"}
    if (
        train_df.empty
        or train_feature_matrix.empty
        or symbol_rows.empty
        or symbol_feature_matrix.empty
        or not required_base_cols.issubset(train_df.columns)
        or not required_base_cols.issubset(symbol_rows.columns)
    ):
        return None

    history = (
        train_df[["symbol", "trade_date", "close", target_col]]
        .reset_index(drop=True)
        .join(train_feature_matrix.drop(columns=["symbol"], errors="ignore").reset_index(drop=True))
    )
    query = (
        symbol_rows[["symbol", "trade_date", "close"]]
        .reset_index(drop=True)
        .join(symbol_feature_matrix.drop(columns=["symbol"], errors="ignore").reset_index(drop=True))
    )

    try:
        return find_similar_historical_periods(
            history,
            query,
            target_col=target_col,
        )
    except Exception as exc:
        logger.warning("Failed to build historical similarity summary: %s", exc, exc_info=True)
        return None


def generate_comparison_report(
    results: Dict[str, Dict],
    symbol: str,
    date_range: tuple[str, str],
    X: pd.DataFrame,
    dl_config: Any | None = None,
) -> Dict[str, Any]:
    """Generate a structured LightGBM report.

    The ``dl_config`` argument is retained only as a backward-compatible no-op
    so older call sites do not crash after GRU/LSTM removal.
    """

    del dl_config

    if X.empty:
        raise ValueError("Feature matrix X is empty")
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        raise ValueError(f"date_range must be tuple of (start_date, end_date), got {type(date_range)}")

    start_date, end_date = date_range
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise ValueError(
            "date_range elements must be strings in YYYY-MM-DD format, "
            f"got ({type(start_date)}, {type(end_date)})"
        )
    if "lightgbm" not in results:
        raise ValueError("results missing 'lightgbm'")

    predictions = {
        model_name: result["prediction"]
        for model_name, result in results.items()
    }
    metrics = {
        model_name: result["metrics"]
        for model_name, result in results.items()
    }

    lgbm_metrics = metrics["lightgbm"]
    if "mean_auc" not in lgbm_metrics:
        raise ValueError("Model lightgbm missing 'mean_auc' in metrics")
    lgbm_metrics = dict(lgbm_metrics)
    lgbm_metrics.update(_extract_requested_symbol_metrics(lgbm_metrics, symbol))
    metrics["lightgbm"] = lgbm_metrics

    lgbm_model = results["lightgbm"]["model"]
    parameters = {
        "lightgbm": _extract_parameters(lgbm_model, "lightgbm"),
    }
    fusion_score = _calculate_fusion_score(predictions, metrics)

    feature_importance: Dict[str, Any] = {}
    lgbm_X = results["lightgbm"].get("feature_matrix", X)
    top_features = _extract_feature_importance(lgbm_model, lgbm_X, top_k=3)
    if top_features:
        feature_importance["lightgbm"] = {"top_features": top_features}

    report: Dict[str, Any] = {
        "metadata": {
            "symbol": symbol,
            "date_range": date_range,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_points": len(X),
        },
        "parameters": parameters,
        "metrics": metrics,
        "predictions": {
            "lightgbm": predictions["lightgbm"],
            "fusion_score": fusion_score,
        },
        "feature_importance": feature_importance,
    }

    historical_similarity = results["lightgbm"].get("historical_similarity")
    if historical_similarity:
        report["historical_similarity"] = historical_similarity

    return report


def train_all_models(
    X: pd.DataFrame | None = None,
    y: pd.Series | None = None,
    symbol: str | None = None,
    model_types: List[str] | None = None,
    dl_config: Any | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> Dict[str, Dict]:
    """Train the repository's single supported model: panel LightGBM."""

    del dl_config

    model_types = _normalize_model_types(model_types)

    lgbm_X: pd.DataFrame | None = None
    lgbm_y: pd.Series | None = None
    lgbm_trade_dates: pd.Series | None = None
    lgbm_text: pd.Series | None = None
    lgbm_train_df: pd.DataFrame | None = None
    lgbm_symbol_rows: pd.DataFrame | None = None

    if X is None or y is None:
        if symbol is None:
            raise ValueError("Must provide either (X, y) or symbol")
        symbol_norm = symbol.strip().upper()
        (
            lgbm_train_df,
            lgbm_X,
            lgbm_y,
            lgbm_trade_dates,
            lgbm_text,
            lgbm_symbol_rows,
        ) = _load_panel_lightgbm_dataset(
            symbol_norm,
            start_date=start_date,
            end_date=end_date,
        )
    else:
        if X.empty or y.empty:
            raise ValueError("Feature matrix X or target y is empty")
        lgbm_X = X
        lgbm_y = y

    results: Dict[str, Dict[str, Any]] = {}

    if "lightgbm" in model_types:
        logger.info("Training LightGBM")
        if lgbm_X is None or lgbm_y is None:
            raise ValueError("LightGBM feature matrix is empty")

        if (
            symbol is not None
            and lgbm_trade_dates is not None
            and lgbm_text is not None
            and lgbm_symbol_rows is not None
        ):
            lgbm_model, lgbm_metrics, text_artifacts, lgbm_feature_matrix = train_lightgbm_panel_with_text(
                lgbm_X,
                lgbm_y,
                lgbm_trade_dates,
                lgbm_text,
                categorical_features=["symbol"],
                n_splits=5,
            )
            symbol_text_features = transform_text_svd_features(
                lgbm_symbol_rows[TEXT_BLOB_COL],
                text_artifacts,
            )
            lgbm_symbol_feature_matrix = (
                lgbm_symbol_rows[PANEL_FEATURE_COLS]
                .reset_index(drop=True)
                .join(symbol_text_features.reset_index(drop=True))
            )
            lgbm_latest_features = lgbm_symbol_feature_matrix.tail(1)
            lgbm_pred = predict_proba_latest(lgbm_model, lgbm_latest_features)
            lgbm_metrics = dict(lgbm_metrics)
            lgbm_metrics["training_scope"] = DEFAULT_LIGHTGBM_SCOPE
            lgbm_metrics["target"] = DEFAULT_SYMBOL_TARGET_COL
            lgbm_metrics.update(_extract_requested_symbol_metrics(lgbm_metrics, symbol_norm))
            historical_similarity = _build_historical_similarity_summary(
                train_df=lgbm_train_df if lgbm_train_df is not None else pd.DataFrame(),
                train_feature_matrix=lgbm_feature_matrix,
                symbol_rows=lgbm_symbol_rows,
                symbol_feature_matrix=lgbm_symbol_feature_matrix,
            )
        else:
            lgbm_model, lgbm_metrics = train_lightgbm(lgbm_X, lgbm_y, n_splits=5)
            lgbm_pred = predict_proba_latest(lgbm_model, lgbm_X)
            lgbm_metrics = dict(lgbm_metrics)
            lgbm_metrics["training_scope"] = "provided_dataset"
            lgbm_feature_matrix = lgbm_X
            historical_similarity = None

        results["lightgbm"] = {
            "model": lgbm_model,
            "metrics": lgbm_metrics,
            "prediction": lgbm_pred,
            "feature_matrix": lgbm_feature_matrix,
        }
        if historical_similarity:
            results["lightgbm"]["historical_similarity"] = historical_similarity

        logger.info("LightGBM - AUC: %.4f", lgbm_metrics["mean_auc"])

    return results


def format_comparison_markdown(report: Dict[str, Any]) -> str:
    """Format the LightGBM report as a complete Markdown document."""

    if "metadata" not in report:
        raise ValueError("Report missing 'metadata' section")
    if "parameters" not in report:
        raise ValueError("Report missing 'parameters' section")
    if "metrics" not in report:
        raise ValueError("Report missing 'metrics' section")
    if "predictions" not in report:
        raise ValueError("Report missing 'predictions' section")

    metadata = report["metadata"]
    parameters = report["parameters"].get("lightgbm", {})
    metrics = report["metrics"].get("lightgbm", {})
    predictions = report["predictions"]

    date_range = metadata.get("date_range", ("N/A", "N/A"))
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_str = f"{date_range[0]} 至 {date_range[1]}"
    else:
        date_str = "N/A"

    lines: List[str] = []
    lines.append("# LightGBM 面板模型报告\n")
    lines.append("## 报告元数据\n")
    lines.append(f"- **股票代码**: {metadata.get('symbol', 'N/A')}")
    lines.append(f"- **时间范围**: {date_str}")
    lines.append(f"- **数据点数**: {metadata.get('data_points', 'N/A')}")
    lines.append(f"- **生成时间**: {metadata.get('generated_at', 'N/A')}\n")

    lines.append("## 模型参数\n")
    lines.append("| 参数 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| Objective | {parameters.get('objective', 'N/A')} |")
    lines.append(f"| Learning Rate | {parameters.get('learning_rate', 'N/A')} |")
    lines.append(f"| Num Estimators | {parameters.get('n_estimators', 'N/A')} |")
    lines.append(f"| Num Leaves | {parameters.get('num_leaves', 'N/A')} |")
    lines.append(f"| Max Depth | {parameters.get('max_depth', 'N/A')} |")
    lines.append(f"| Regularization | {parameters.get('reg_lambda', 'N/A')} |")
    lines.append(f"| Training Scope | {metrics.get('training_scope', 'N/A')} |\n")

    lines.append("## 性能指标\n")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| Mean AUC | {_format_float(metrics.get('mean_auc'))} |")
    lines.append(f"| Mean Accuracy | {_format_float(metrics.get('mean_accuracy'))} |")
    requested_symbol = metrics.get("requested_symbol", metadata.get("symbol"))
    lines.append(f"| 当前标的 OOS AUC | {_format_float(metrics.get('requested_symbol_auc'))} |")
    lines.append(f"| 当前标的 OOS Accuracy | {_format_float(metrics.get('requested_symbol_accuracy'))} |")
    requested_eval_rows = metrics.get("requested_symbol_eval_rows")
    if isinstance(requested_eval_rows, (int, float, np.integer, np.floating)) and math.isfinite(float(requested_eval_rows)):
        requested_eval_rows_str = str(int(requested_eval_rows))
    else:
        requested_eval_rows_str = "N/A"
    lines.append(f"| 当前标的验证样本数 | {requested_eval_rows_str} |")
    training_time = metrics.get("training_time_seconds", metrics.get("training_time", "N/A"))
    training_time_str = f"{float(training_time):.2f}秒" if _is_finite_number(training_time) else "N/A"
    lines.append(f"| Training Time | {training_time_str} |")
    lines.append(f"| Cross Validation | {metrics.get('train_test_split', 'N/A')} |\n")
    if metrics.get("requested_symbol_auc_unavailable") and requested_symbol:
        lines.append(
            f"注：`{requested_symbol}` 在当前外样本折中缺少正负双边标签，单票 AUC 暂不可用。\n"
        )

    lines.append("## 最新预测信号\n")
    lines.append("| 项目 | 数值 |")
    lines.append("|------|------|")
    lightgbm_pred = predictions.get("lightgbm")
    fusion_score = predictions.get("fusion_score")
    lightgbm_signal = "看涨" if _is_finite_number(lightgbm_pred) and float(lightgbm_pred) > 0.5 else "看跌"
    composite_signal = "看涨" if _is_finite_number(fusion_score) and float(fusion_score) > 0.5 else "看跌"
    lines.append(f"| LightGBM 概率 | {_format_percent_from_probability(lightgbm_pred)} ({lightgbm_signal if _is_finite_number(lightgbm_pred) else 'N/A'}) |")
    lines.append(f"| 综合信号 | {_format_percent_from_probability(fusion_score)} ({composite_signal if _is_finite_number(fusion_score) else 'N/A'}) |\n")
    lines.append("当前系统已统一为单一 LightGBM 面板模型，综合信号等同于模型输出。\n")

    lines.append("## LightGBM 特征重要性\n")
    top_features = report.get("feature_importance", {}).get("lightgbm", {}).get("top_features", [])
    if top_features:
        lines.append("| 特征名称 | 重要性得分 |")
        lines.append("|----------|-----------|")
        for feat in top_features:
            lines.append(f"| {feat.get('name', 'N/A')} | {int(round(feat.get('importance', 0)))} |")
        lines.append("")
    else:
        lines.append("无可用特征重要性数据\n")

    historical_similarity = report.get("historical_similarity")
    if historical_similarity and historical_similarity.get("n_matches", 0) > 0:
        lines.append("## 历史相似阶段\n")
        avg_sim = float(historical_similarity.get("avg_similarity", 0.0)) * 100.0
        avg_ret = float(historical_similarity.get("avg_future_return_3d", 0.0)) * 100.0
        positive_rate = float(historical_similarity.get("positive_rate", 0.0)) * 100.0
        hit_rate = float(historical_similarity.get("target_hit_rate", 0.0)) * 100.0
        same_symbol_matches = int(historical_similarity.get("same_symbol_matches", 0))
        peer_group_matches = int(historical_similarity.get("peer_group_matches", 0))
        market_matches = int(historical_similarity.get("market_matches", 0))
        horizon_days = historical_similarity.get("horizon_days", 3)
        lines.append(
            f"- 系统找到 **{historical_similarity.get('n_matches', 0)} 个** 与当前状态高度相似的历史窗口，"
            f"平均相似度约 **{avg_sim:.1f}%**。"
        )
        lines.append(
            f"- 匹配策略为 **同股票优先、peer group 次优先、全市场兜底**："
            f"同股票 {same_symbol_matches} 个，peer group {peer_group_matches} 个，"
            f"全市场补充 {market_matches} 个。"
        )
        lines.append(
            f"- 这些窗口在随后 {horizon_days} 个交易日的平均收益约 **{avg_ret:+.2f}%**，"
            f"正收益占比约 **{positive_rate:.1f}%**，"
            f"上涨异动命中率约 **{hit_rate:.1f}%**。"
        )
        matches = historical_similarity.get("matches", [])[:3]
        if matches:
            lines.append("")
            lines.append("| 相似标的 | 窗口区间 | 相似度 | 随后3日收益 |")
            lines.append("|----------|----------|--------|-------------|")
            for match in matches:
                scope_label = {
                    "same_symbol": "同股票",
                    "peer_group": "peer group",
                    "market": "全市场",
                }.get(str(match.get("scope", "market")), "全市场")
                lines.append(
                    f"| {match.get('symbol', 'N/A')} ({scope_label}) | "
                    f"{match.get('start_date', 'N/A')} ~ {match.get('end_date', 'N/A')} | "
                    f"{float(match.get('similarity', 0.0)) * 100.0:.1f}% | "
                    f"{float(match.get('future_return_3d', 0.0)) * 100.0:+.2f}% |"
                )
            lines.append("")

    lines.append("## 综合评估\n")
    lines.append("- 当前量化系统已统一为单一 LightGBM 面板模型。")
    mean_auc = metrics.get("mean_auc")
    requested_symbol_auc = metrics.get("requested_symbol_auc")
    if _is_finite_number(requested_symbol_auc) and requested_symbol:
        lines.append(
            f"- 当前标的 `{requested_symbol}` 的外样本 AUC 为 {_format_float(requested_symbol_auc)}，"
            "应优先以此判断单票信号可信度。"
        )
    elif metrics.get("requested_symbol_auc_unavailable") and requested_symbol:
        lines.append(
            f"- 当前标的 `{requested_symbol}` 的单票 AUC 暂不可用，说明验证期标签分布过于单边。"
        )
    if _is_finite_number(mean_auc):
        if float(mean_auc) >= 0.60:
            lines.append("- 模型区分度较强，可以把概率信号作为优先参考。")
        elif float(mean_auc) >= 0.55:
            lines.append("- 模型区分度中等，建议结合历史相似阶段和基本面事件共同判断。")
        else:
            lines.append("- 模型区分度有限，建议把结果作为辅助信号而非单独决策依据。")
    else:
        lines.append("- 当前评估指标不足，建议先检查训练数据完整性。")

    return "\n".join(lines)


def format_predictions_for_agent(results: Dict[str, Dict]) -> str:
    """Format LightGBM predictions as Markdown for CIO Agent."""

    if "lightgbm" not in results:
        raise ValueError("results missing 'lightgbm'")

    result = results["lightgbm"]
    metrics = result["metrics"]
    pred = result["prediction"]

    lines = ["## 量化模型预测汇总\n"]
    lines.append("### LIGHTGBM 分析师")
    if _is_finite_number(pred):
        pred_text = f"{float(pred):.2%} {'看涨' if float(pred) > 0.5 else '看跌'}"
    else:
        pred_text = "N/A"
    lines.append(f"- **预测概率**: {pred_text}")
    lines.append(f"- **模型AUC**: {_format_float(metrics.get('mean_auc'))}")
    lines.append(f"- **模型准确率**: {_format_float(metrics.get('mean_accuracy'))}")
    requested_symbol = metrics.get("requested_symbol")
    if _is_finite_number(metrics.get("requested_symbol_auc")) and requested_symbol:
        lines.append(
            f"- **当前标的OOS AUC**: `{requested_symbol}` = {_format_float(metrics.get('requested_symbol_auc'))}"
        )
    elif metrics.get("requested_symbol_auc_unavailable") and requested_symbol:
        lines.append(f"- **当前标的OOS AUC**: `{requested_symbol}` 暂不可用（验证期单边标签）")

    if metrics.get("training_scope") == DEFAULT_LIGHTGBM_SCOPE:
        lines.append("- **分析依据**: 基于全市场 panel 因子、市场残差、文本 SVD 和近期动量")
    else:
        lines.append("- **分析依据**: 基于截面因子和近期动量")

    historical_similarity = result.get("historical_similarity")
    if historical_similarity and historical_similarity.get("n_matches", 0) > 0:
        avg_ret = float(historical_similarity.get("avg_future_return_3d", 0.0)) * 100.0
        hit_rate = float(historical_similarity.get("target_hit_rate", 0.0)) * 100.0
        same_symbol_matches = int(historical_similarity.get("same_symbol_matches", 0))
        peer_group_matches = int(historical_similarity.get("peer_group_matches", 0))
        market_matches = int(historical_similarity.get("market_matches", 0))
        top_match = (historical_similarity.get("matches") or [{}])[0]
        top_symbol = top_match.get("symbol", "N/A")
        lines.append(
            f"- **历史相似期**: 匹配到 {historical_similarity.get('n_matches', 0)} 个高相似窗口，"
            f"随后 3 日平均收益约 {avg_ret:+.2f}%，异动命中率约 {hit_rate:.1f}%，"
            f"同股票 {same_symbol_matches} 个、peer group {peer_group_matches} 个、"
            f"全市场补充 {market_matches} 个，最接近样本来自 `{top_symbol}`。"
        )

    return "\n".join(lines) + "\n"
