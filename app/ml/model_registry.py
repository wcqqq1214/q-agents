"""Model registry for multi-model orchestration.

Provides unified interface for training and predicting with multiple models
(LightGBM, GRU, LSTM) and formatting results for CIO Agent consumption.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Literal

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import RobustScaler

from app.ml.dl_config import COLUMNS_TO_SCALE, PASSTHROUGH_COLUMNS, DLConfig
from app.ml.dl_trainer import train_dl_model
from app.ml.features import (
    FEATURE_COLS,
    PANEL_FEATURE_COLS,
    TEXT_BLOB_COL,
    build_features,
    build_panel_features,
)
from app.ml.model_trainer import (
    predict_proba_latest,
    train_lightgbm,
    train_lightgbm_panel_with_text,
)
from app.ml.similarity import HistoricalSimilaritySummary, find_similar_historical_periods
from app.ml.text_features import transform_text_svd_features

logger = logging.getLogger(__name__)

ModelType = Literal["lightgbm", "gru", "lstm"]
DEFAULT_SYMBOL_TARGET_COL = "target_up_big_move_t3"
DEFAULT_LIGHTGBM_SCOPE = "panel"
DEFAULT_DL_SCOPE = "single_symbol"


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


def _extract_parameters(model: Any, model_type: str, dl_config: DLConfig | None = None) -> Dict[str, Any]:
    """Extract parameters from heterogeneous models.

    Args:
        model: Trained model (LGBMClassifier or PyTorch nn.Module)
        model_type: "lightgbm", "gru", or "lstm"
        dl_config: DLConfig instance for PyTorch models

    Returns:
        Dictionary of model parameters
    """
    if model_type == "lightgbm":
        return model.get_params()
    elif model_type in ["gru", "lstm"]:
        if dl_config is None:
            raise ValueError(f"DLConfig required for {model_type}")
        return {
            "hidden_size": dl_config.hidden_size,
            "num_layers": dl_config.num_layers,
            "dropout": dl_config.dropout,
            "seq_len": dl_config.seq_len,
            "learning_rate": dl_config.learning_rate,
            "weight_decay": dl_config.weight_decay,
            "batch_size": dl_config.batch_size,
            "max_epochs": dl_config.max_epochs,
        }
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def _calculate_fusion_score(predictions: Dict[str, float], metrics: Dict[str, Dict[str, float]]) -> float:
    """Calculate weighted average fusion score.

    Weight = Mean AUC of each model

    Args:
        predictions: Dict with keys "lightgbm", "gru", "lstm" and float values (0-1)
        metrics: Dict with same keys, each containing "mean_auc" field

    Returns:
        Fusion score (0-1)

    Raises:
        ValueError: If any model in predictions lacks metrics
    """
    # Validate all models have metrics
    missing_models = [m for m in predictions.keys() if m not in metrics]
    if missing_models:
        logger.warning(f"Missing metrics for models: {missing_models}. Falling back to simple mean.")
        finite_predictions = [float(pred) for pred in predictions.values() if _is_finite_number(pred)]
        return float(np.mean(finite_predictions)) if finite_predictions else float("nan")

    auc_values = [metrics[m]["mean_auc"] for m in predictions.keys()]
    if any(not _is_finite_number(auc) for auc in auc_values):
        logger.warning("Non-finite AUC detected. Falling back to simple mean.")
        finite_predictions = [float(pred) for pred in predictions.values() if _is_finite_number(pred)]
        return float(np.mean(finite_predictions)) if finite_predictions else float("nan")

    total_auc = sum(float(metrics[m]["mean_auc"]) for m in predictions.keys())
    if total_auc == 0:
        logger.warning("Total AUC is 0. Falling back to simple mean.")
        finite_predictions = [float(pred) for pred in predictions.values() if _is_finite_number(pred)]
        return float(np.mean(finite_predictions)) if finite_predictions else float("nan")

    fusion = sum(
        float(predictions[m]) * float(metrics[m]["mean_auc"]) / total_auc
        for m in predictions.keys()
    )
    return float(fusion)


def _extract_feature_importance(model: Any, X: pd.DataFrame, top_k: int = 3) -> List[Dict[str, Any]]:
    """Extract top K feature importances from LightGBM model.

    Args:
        model: Trained LGBMClassifier
        X: Feature matrix (used to get feature names from columns)
        top_k: Number of top features to extract

    Returns:
        List of dicts with "name" and "importance" keys
    """
    try:
        importances = model.feature_importances_
        feature_names = X.columns.tolist()

        if len(feature_names) == 0 or len(importances) == 0:
            logger.warning("Empty feature names or importances")
            return []

        # Ensure lengths match
        if len(importances) != len(feature_names):
            logger.warning(f"Feature count mismatch: {len(importances)} importances vs {len(feature_names)} names")
            return []

        # Clamp top_k to available features
        clamped_k = min(top_k, len(importances))
        top_indices = np.argsort(importances)[-clamped_k:][::-1]
        return [
            {
                "name": str(feature_names[i]),
                "importance": float(importances[i])
            }
            for i in top_indices
        ]
    except Exception as e:
        logger.error(f"Failed to extract feature importance: {e}")
        return []


def _load_symbol_dataset(
    symbol: str,
    target_col: str = DEFAULT_SYMBOL_TARGET_COL,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Load a single-symbol dataset for sequential models."""

    df = build_features(symbol, start_date=start_date, end_date=end_date)
    if df.empty:
        raise ValueError(f"No features available for {symbol}")

    data = df.dropna(subset=[target_col]).reset_index(drop=True)
    if data.empty:
        raise ValueError(f"No labeled rows available for {symbol} and target {target_col}")

    X = data[FEATURE_COLS]
    y = data[target_col].astype(int)
    return data, X, y


def _load_panel_lightgbm_dataset(
    symbol: str,
    target_col: str = DEFAULT_SYMBOL_TARGET_COL,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.DataFrame]:
    """Load the unified panel dataset and latest inference row for one symbol."""

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
    dl_config: DLConfig | None = None,
) -> Dict[str, Any]:
    """Generate structured comparison report from multi-model results.

    Args:
        results: Output from train_all_models()
        symbol: Stock ticker (e.g., "AAPL")
        date_range: Tuple (start_date, end_date) in "YYYY-MM-DD" format
        X: Feature matrix (for validation and feature importance)
        dl_config: DLConfig instance for PyTorch models

    Returns:
        Structured report dict with metadata, parameters, metrics, predictions

    Raises:
        ValueError: If date_range doesn't match X or required data missing
    """
    if X.empty:
        raise ValueError("Feature matrix X is empty")

    # Validate date_range format
    if not isinstance(date_range, tuple) or len(date_range) != 2:
        raise ValueError(f"date_range must be tuple of (start_date, end_date), got {type(date_range)}")
    start_date, end_date = date_range
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise ValueError(f"date_range elements must be strings in YYYY-MM-DD format, got ({type(start_date)}, {type(end_date)})")

    # Extract predictions
    predictions = {
        model_name: result["prediction"]
        for model_name, result in results.items()
    }

    # Extract metrics
    metrics = {
        model_name: result["metrics"]
        for model_name, result in results.items()
    }

    # Validate all models have mean_auc in metrics
    for model_name, model_metrics in metrics.items():
        if "mean_auc" not in model_metrics:
            raise ValueError(f"Model {model_name} missing 'mean_auc' in metrics. Available keys: {list(model_metrics.keys())}")

    # Extract parameters
    parameters = {}
    for model_name, result in results.items():
        model = result["model"]
        try:
            parameters[model_name] = _extract_parameters(model, model_name, dl_config)
        except Exception as e:
            logger.error(f"Failed to extract parameters for {model_name}: {e}")
            parameters[model_name] = {}

    # Calculate fusion score
    fusion_score = _calculate_fusion_score(predictions, metrics)

    # Extract feature importance (LightGBM only)
    feature_importance = {}
    if "lightgbm" in results:
        lgbm_model = results["lightgbm"]["model"]
        lgbm_X = results["lightgbm"].get("feature_matrix", X)
        try:
            top_features = _extract_feature_importance(lgbm_model, lgbm_X, top_k=3)
            if top_features:
                feature_importance["lightgbm"] = {"top_features": top_features}
            else:
                logger.warning("LightGBM feature importance extraction returned empty list")
        except AttributeError as e:
            logger.error(f"LightGBM model missing feature_importances_ attribute: {e}")
        except ValueError as e:
            logger.error(f"Invalid feature importance data for LightGBM: {e}")
        except Exception as e:
            logger.error(f"Unexpected error extracting LightGBM feature importance: {e}", exc_info=True)

    # Build report
    report = {
        "metadata": {
            "symbol": symbol,
            "date_range": date_range,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_points": len(X),
        },
        "parameters": parameters,
        "metrics": metrics,
        "predictions": {**predictions, "fusion_score": fusion_score},
        "feature_importance": feature_importance,
    }
    historical_similarity = results.get("lightgbm", {}).get("historical_similarity")
    if historical_similarity:
        report["historical_similarity"] = historical_similarity

    return report


def train_all_models(
    X: pd.DataFrame | None = None,
    y: pd.Series | None = None,
    symbol: str | None = None,
    model_types: List[ModelType] | None = None,
    dl_config: DLConfig | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> Dict[str, Dict]:
    """Train multiple models and return predictions.

    For parallel architecture (Phase D): trains LightGBM and DL models,
    provides multi-dimensional "expert opinions" for CIO Agent.

    Can be called in two ways:
    1. With X, y directly (for testing or external datasets)
    2. With symbol (for production: LightGBM uses unified panel data; DL uses
       the single-symbol sequence)

    Args:
        X: Feature matrix (optional, use if not providing symbol)
        y: Target series (optional, use if not providing symbol)
        symbol: Stock ticker (e.g., "AAPL") - alternative to X, y
        model_types: Models to train, default ["lightgbm", "gru"]
        dl_config: DL configuration, default DLConfig()
        start_date: Optional lower date bound when loading by symbol
        end_date: Optional upper date bound when loading by symbol

    Returns:
        {
            "lightgbm": {
                "model": LGBMClassifier,
                "metrics": {...},
                "prediction": float,
            },
            "gru": {
                "model": nn.Module,
                "metrics": {...},
                "scaler": RobustScaler,
                "prediction": float,
            },
        }

    Raises:
        ValueError: If neither (X, y) nor symbol provided, or if no features available
    """
    if model_types is None:
        model_types = ["lightgbm", "gru"]

    if dl_config is None:
        dl_config = DLConfig()

    lgbm_X: pd.DataFrame | None = None
    lgbm_y: pd.Series | None = None
    lgbm_trade_dates: pd.Series | None = None
    lgbm_text: pd.Series | None = None
    lgbm_train_df: pd.DataFrame | None = None
    lgbm_symbol_rows: pd.DataFrame | None = None
    dl_X: pd.DataFrame | None = None
    dl_y: pd.Series | None = None

    # Load features
    if X is None or y is None:
        if symbol is None:
            raise ValueError("Must provide either (X, y) or symbol")
        symbol_norm = symbol.strip().upper()
        wants_lightgbm = "lightgbm" in model_types
        wants_dl = any(model_type in model_types for model_type in ["gru", "lstm"])

        if wants_dl:
            _, dl_X, dl_y = _load_symbol_dataset(
                symbol_norm,
                start_date=start_date,
                end_date=end_date,
            )
        if wants_lightgbm:
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
        dl_X = X
        dl_y = y

    results = {}

    # Train LightGBM
    if "lightgbm" in model_types:
        logger.info("Training LightGBM")
        try:
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
            logger.info(f"LightGBM - AUC: {lgbm_metrics['mean_auc']:.4f}")
        except Exception as e:
            logger.error(f"LightGBM training failed: {e}")

    # Train DL models
    for model_type in ["gru", "lstm"]:
        if model_type not in model_types:
            continue

        logger.info(f"Training {model_type.upper()}")
        try:
            if dl_X is None or dl_y is None:
                raise ValueError(f"{model_type.upper()} feature matrix is empty")
            dl_config.model_type = model_type
            # CRITICAL FIX: train_dl_model now returns (model, metrics, scaler)
            dl_model, dl_metrics, dl_scaler = train_dl_model(dl_X, dl_y, config=dl_config)
            # CRITICAL FIX: Pass scaler to predict_proba_latest_dl
            dl_pred = predict_proba_latest_dl(dl_model, dl_X, dl_config, dl_scaler)
            dl_metrics = dict(dl_metrics)
            if symbol is not None:
                dl_metrics["training_scope"] = DEFAULT_DL_SCOPE
                dl_metrics["target"] = DEFAULT_SYMBOL_TARGET_COL
            else:
                dl_metrics["training_scope"] = "provided_dataset"

            results[model_type] = {
                "model": dl_model,
                "metrics": dl_metrics,
                "scaler": dl_scaler,  # Save scaler for later inference
                "prediction": dl_pred,
            }
            logger.info(f"{model_type.upper()} - AUC: {dl_metrics['mean_auc']:.4f}")
        except Exception as e:
            logger.error(f"{model_type.upper()} training failed: {e}", exc_info=True)

    return results


def predict_proba_latest_dl(
    model: torch.nn.Module,
    X: pd.DataFrame,
    config: DLConfig,
    scaler: RobustScaler,
) -> float:
    """Predict latest day probability using DL model.

    CRITICAL: Uses provided scaler to prevent distribution mismatch between
    training and inference. Scaler must be from training set.

    Args:
        model: Trained DL model
        X: Full feature matrix
        config: DL configuration
        scaler: Fitted scaler from training (prevents distribution mismatch)

    Returns:
        Prediction probability (0-1)

    Raises:
        ValueError: If insufficient data for prediction
    """
    if X.empty or len(X) < config.seq_len:
        raise ValueError("Insufficient data for prediction")

    # Take last seq_len days
    X_recent = X.iloc[-config.seq_len:].copy()

    # Scale using provided scaler (CRITICAL FIX: use transform, NOT fit_transform)
    scale_cols = [c for c in COLUMNS_TO_SCALE if c in X.columns]
    pass_cols = [c for c in PASSTHROUGH_COLUMNS if c in X.columns]

    # Fallback: if no columns matched, use all columns
    if not scale_cols and not pass_cols:
        scale_cols = list(X.columns)
        pass_cols = []

    X_scaled = X.copy()
    if scale_cols:
        # CRITICAL FIX: Use transform() to apply training distribution
        X_scaled[scale_cols] = scaler.transform(X[scale_cols])

    all_cols = scale_cols + pass_cols
    X_scaled = X_scaled[all_cols].iloc[-config.seq_len:].values

    # Predict
    X_tensor = torch.FloatTensor(X_scaled).unsqueeze(0).to(config.device)

    model.eval()
    with torch.no_grad():
        logits = model(X_tensor)
        proba = torch.sigmoid(logits).cpu().item()

    return float(proba)


def format_comparison_markdown(report: Dict[str, Any]) -> str:
    """Format comparison report as complete Markdown document.

    Generates a full multi-section Markdown report covering:
    - Header and report metadata (symbol, date range, data points, generation time)
    - Model parameter comparison table (data processing, network structure, training config)
    - Performance metrics table (Mean AUC, Mean Accuracy, Training Time)
    - Latest prediction signals with fusion score
    - LightGBM feature importance table (top features by importance score)
    - Comprehensive assessment (model strengths, fusion recommendation, risk disclaimer)

    The fusion recommendation is dynamically generated based on AUC spread across models:
    if max AUC - min AUC < 0.05, signals are considered consistent; otherwise highlights
    the best-performing model.

    Note: This report is a quantitative analysis tool output and does not constitute
    investment advice.

    Args:
        report: Output from generate_comparison_report()

    Returns:
        Formatted Markdown string covering all sections listed above

    Raises:
        ValueError: If report missing required sections ('metadata', 'parameters',
            'metrics', or 'predictions')
    """
    if "metadata" not in report:
        raise ValueError("Report missing 'metadata' section")
    if "parameters" not in report:
        raise ValueError("Report missing 'parameters' section")

    lines = []

    # Header
    lines.append("# 量化预测模型对比报告\n")

    # Metadata section
    metadata = report["metadata"]
    symbol = metadata.get("symbol", "N/A")
    date_range = metadata.get("date_range", ("N/A", "N/A"))
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_str = f"{date_range[0]} 至 {date_range[1]}"
    else:
        date_str = "N/A"
    data_points = metadata.get("data_points", "N/A")
    generated_at = metadata.get("generated_at", "N/A")

    lines.append("## 报告元数据\n")
    lines.append(f"- **股票代码**: {symbol}")
    lines.append(f"- **时间范围**: {date_str}")
    lines.append(f"- **数据点数**: {data_points}")
    lines.append(f"- **生成时间**: {generated_at}\n")

    # Parameters section
    parameters = report["parameters"]
    lines.append("## 模型参数对比\n")

    # Data Processing subsection
    lines.append("### 数据处理 (Data Processing)\n")
    lines.append("| 参数 | LightGBM | GRU | LSTM |")
    lines.append("|------|----------|-----|------|")

    # Core perspective
    lgbm_perspective = parameters.get("lightgbm", {}).get("objective", "N/A")
    gru_perspective = "时间序列"
    lstm_perspective = "时间序列"
    lines.append(f"| Core Perspective | {lgbm_perspective} | {gru_perspective} | {lstm_perspective} |")

    # Lookback window
    lgbm_lookback = "N/A"
    gru_lookback = parameters.get("gru", {}).get("seq_len", "N/A")
    lstm_lookback = parameters.get("lstm", {}).get("seq_len", "N/A")
    lines.append(f"| Lookback Window | {lgbm_lookback} | {gru_lookback} | {lstm_lookback} |")

    # Normalization
    lgbm_norm = "无"
    gru_norm = "RobustScaler"
    lstm_norm = "RobustScaler"
    lines.append(f"| Normalization | {lgbm_norm} | {gru_norm} | {lstm_norm} |\n")

    # Network Structure subsection
    lines.append("### 网络结构 (Network Structure)\n")
    lines.append("| 参数 | LightGBM | GRU | LSTM |")
    lines.append("|------|----------|-----|------|")

    # Hidden size
    lgbm_hidden = "N/A"
    gru_hidden = parameters.get("gru", {}).get("hidden_size", "N/A")
    lstm_hidden = parameters.get("lstm", {}).get("hidden_size", "N/A")
    lines.append(f"| Hidden Size | {lgbm_hidden} | {gru_hidden} | {lstm_hidden} |")

    # Number of layers
    lgbm_layers = "N/A"
    gru_layers = parameters.get("gru", {}).get("num_layers", "N/A")
    lstm_layers = parameters.get("lstm", {}).get("num_layers", "N/A")
    lines.append(f"| Num Layers | {lgbm_layers} | {gru_layers} | {lstm_layers} |")

    # Dropout
    lgbm_dropout = "N/A"
    gru_dropout = parameters.get("gru", {}).get("dropout", "N/A")
    lstm_dropout = parameters.get("lstm", {}).get("dropout", "N/A")
    lines.append(f"| Dropout | {lgbm_dropout} | {gru_dropout} | {lstm_dropout} |\n")

    # Training Config subsection
    lines.append("### 训练配置 (Training Config)\n")
    lines.append("| 参数 | LightGBM | GRU | LSTM |")
    lines.append("|------|----------|-----|------|")

    # Learning rate
    lgbm_lr = parameters.get("lightgbm", {}).get("learning_rate", "N/A")
    gru_lr = parameters.get("gru", {}).get("learning_rate", "N/A")
    lstm_lr = parameters.get("lstm", {}).get("learning_rate", "N/A")
    lines.append(f"| Learning Rate | {lgbm_lr} | {gru_lr} | {lstm_lr} |")

    # Regularization
    lgbm_reg = parameters.get("lightgbm", {}).get("reg_lambda", "N/A")
    gru_reg = parameters.get("gru", {}).get("weight_decay", "N/A")
    lstm_reg = parameters.get("lstm", {}).get("weight_decay", "N/A")
    lines.append(f"| Regularization | {lgbm_reg} | {gru_reg} | {lstm_reg} |")

    # Batch size
    lgbm_batch = "N/A"
    gru_batch = parameters.get("gru", {}).get("batch_size", "N/A")
    lstm_batch = parameters.get("lstm", {}).get("batch_size", "N/A")
    lines.append(f"| Batch Size | {lgbm_batch} | {gru_batch} | {lstm_batch} |")

    # Cross validation
    lgbm_cv = "5-fold"
    gru_cv = "N/A"
    lstm_cv = "N/A"
    lines.append(f"| Cross Validation | {lgbm_cv} | {gru_cv} | {lstm_cv} |\n")

    # Part 2: Metrics and Predictions
    if "metrics" not in report:
        raise ValueError("Report missing 'metrics' section")
    if "predictions" not in report:
        raise ValueError("Report missing 'predictions' section")

    metrics = report["metrics"]
    predictions = report["predictions"]

    # Metrics section
    lines.append("## 性能指标\n")
    lines.append("| 指标 | LightGBM | GRU | LSTM |")
    lines.append("|------|----------|-----|------|")

    # Mean AUC
    lgbm_auc = metrics.get("lightgbm", {}).get("mean_auc", "N/A")
    gru_auc = metrics.get("gru", {}).get("mean_auc", "N/A")
    lstm_auc = metrics.get("lstm", {}).get("mean_auc", "N/A")

    lgbm_auc_str = _format_float(lgbm_auc)
    gru_auc_str = _format_float(gru_auc)
    lstm_auc_str = _format_float(lstm_auc)
    lines.append(f"| Mean AUC | {lgbm_auc_str} | {gru_auc_str} | {lstm_auc_str} |")

    # Mean Accuracy
    lgbm_acc = metrics.get("lightgbm", {}).get("mean_accuracy", "N/A")
    gru_acc = metrics.get("gru", {}).get("mean_accuracy", "N/A")
    lstm_acc = metrics.get("lstm", {}).get("mean_accuracy", "N/A")

    lgbm_acc_str = _format_float(lgbm_acc)
    gru_acc_str = _format_float(gru_acc)
    lstm_acc_str = _format_float(lstm_acc)
    lines.append(f"| Mean Accuracy | {lgbm_acc_str} | {gru_acc_str} | {lstm_acc_str} |")

    # Training time
    lgbm_time = metrics.get("lightgbm", {}).get(
        "training_time_seconds",
        metrics.get("lightgbm", {}).get("training_time", "N/A"),
    )
    gru_time = metrics.get("gru", {}).get(
        "training_time_seconds",
        metrics.get("gru", {}).get("training_time", "N/A"),
    )
    lstm_time = metrics.get("lstm", {}).get(
        "training_time_seconds",
        metrics.get("lstm", {}).get("training_time", "N/A"),
    )

    lgbm_time_str = f"{float(lgbm_time):.2f}秒" if _is_finite_number(lgbm_time) else "N/A"
    gru_time_str = f"{float(gru_time):.2f}秒" if _is_finite_number(gru_time) else "N/A"
    lstm_time_str = f"{float(lstm_time):.2f}秒" if _is_finite_number(lstm_time) else "N/A"
    lines.append(f"| Training Time | {lgbm_time_str} | {gru_time_str} | {lstm_time_str} |\n")

    # Predictions section
    lines.append("## 最新预测信号\n")
    lines.append("| 模型 | 预测概率 | 信号 |")
    lines.append("|------|---------|------|")

    # Individual model predictions
    for model_name in ["lightgbm", "gru", "lstm"]:
        if model_name in predictions and model_name != "fusion_score":
            pred_prob = predictions[model_name]
            if not _is_finite_number(pred_prob):
                pred_pct = "N/A"
                signal = "N/A"
            else:
                pred_pct = f"{float(pred_prob) * 100:.1f}%"
                signal = "看涨" if float(pred_prob) > 0.5 else "看跌"
            lines.append(f"| {model_name.upper()} | {pred_pct} | {signal} |")

    # Fusion signal
    fusion_score = predictions.get("fusion_score", "N/A")
    if _is_finite_number(fusion_score):
        fusion_pct = f"{float(fusion_score) * 100:.1f}%"
        fusion_signal = "看涨" if float(fusion_score) > 0.5 else "看跌"
        lines.append(f"| **融合信号** | **{fusion_pct}** | **{fusion_signal}** |\n")
    else:
        lines.append("| **融合信号** | **N/A** | **N/A** |\n")

    # Fusion algorithm explanation
    lines.append("**融合算法**：加权平均，权重 = 各模型的 Mean AUC\n")

    # Part 3: Feature Importance and Assessment

    # Feature Importance section
    lines.append("## LightGBM 特征重要性\n")
    feature_importance = report.get("feature_importance", {})
    lgbm_fi = feature_importance.get("lightgbm", {})
    top_features = lgbm_fi.get("top_features", [])

    if top_features:
        lines.append("| 特征名称 | 重要性得分 |")
        lines.append("|----------|-----------|")
        for feat in top_features:
            feat_name = feat.get("name", "N/A")
            feat_importance = feat.get("importance", 0)
            feat_importance_int = int(round(feat_importance))
            lines.append(f"| {feat_name} | {feat_importance_int} |")
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
        if same_symbol_matches or peer_group_matches or market_matches:
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
                window = f"{match.get('start_date', 'N/A')} ~ {match.get('end_date', 'N/A')}"
                similarity = float(match.get("similarity", 0.0)) * 100.0
                future_ret = float(match.get("future_return_3d", 0.0)) * 100.0
                scope_label = {
                    "same_symbol": "同股票",
                    "peer_group": "peer group",
                    "market": "全市场",
                }.get(str(match.get("scope", "market")), "全市场")
                lines.append(
                    f"| {match.get('symbol', 'N/A')} ({scope_label}) | {window} | {similarity:.1f}% | {future_ret:+.2f}% |"
                )
            lines.append("")

    # Comprehensive Assessment section
    lines.append("## 综合评估\n")

    # Model strengths subsection
    lines.append("### 各模型优势\n")
    lines.append("- **LightGBM**: 特征可解释性强，训练速度快")
    lines.append("- **GRU**: 适合短期时序依赖捕捉")
    lines.append("- **LSTM**: 擅长长期依赖建模\n")

    # Fusion recommendation subsection
    lines.append("### 融合建议\n")
    lines.append("> 注意：本报告为量化分析工具输出，不构成投资建议。\n")

    # Dynamic recommendation based on AUC spread
    metrics = report.get("metrics", {})
    auc_values = [
        v.get("mean_auc")
        for v in metrics.values()
        if _is_finite_number(v.get("mean_auc"))
    ]
    if len(auc_values) >= 2:
        auc_spread = max(auc_values) - min(auc_values)
        if auc_spread < 0.05:
            lines.append("各模型表现相近，融合信号可信度较高")
        else:
            lines.append("各模型表现差异较大，建议重点参考 AUC 最高的模型")
    else:
        lines.append("各模型表现相近，融合信号可信度较高")

    return "\n".join(lines)


def format_predictions_for_agent(results: Dict[str, Dict]) -> str:
    """Format multi-model predictions as Markdown for CIO Agent.

    Args:
        results: train_all_models output

    Returns:
        Markdown report suitable for CIO Agent consumption
    """
    lines = ["## 量化模型预测汇总\n"]

    for model_name, result in results.items():
        metrics = result["metrics"]
        pred = result["prediction"]

        lines.append(f"### {model_name.upper()} 分析师")
        if _is_finite_number(pred):
            pred_text = f"{float(pred):.2%} {'看涨' if float(pred) > 0.5 else '看跌'}"
        else:
            pred_text = "N/A"
        lines.append(f"- **预测概率**: {pred_text}")
        lines.append(f"- **模型AUC**: {_format_float(metrics.get('mean_auc'))}")
        lines.append(f"- **模型准确率**: {_format_float(metrics.get('mean_accuracy'))}")

        if model_name == "lightgbm":
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
                    f"全市场补充 {market_matches} 个，"
                    f"最接近样本来自 `{top_symbol}`。"
                )
        elif model_name == "gru":
            seq_len = metrics.get("seq_len", 15)
            lines.append(f"- **分析依据**: 基于过去{seq_len}天的K线序列形态")
        elif model_name == "lstm":
            seq_len = metrics.get("seq_len", 15)
            lines.append(f"- **分析依据**: 基于过去{seq_len}天的长短期记忆模式")

        lines.append("")

    return "\n".join(lines)
