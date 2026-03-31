"""Model registry for multi-model orchestration.

Provides unified interface for training and predicting with multiple models
(LightGBM, GRU, LSTM) and formatting results for CIO Agent consumption.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Literal

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import RobustScaler

from app.ml.dl_config import COLUMNS_TO_SCALE, PASSTHROUGH_COLUMNS, DLConfig
from app.ml.dl_trainer import train_dl_model
from app.ml.features import FEATURE_COLS, build_features
from app.ml.model_trainer import predict_proba_latest, train_lightgbm

logger = logging.getLogger(__name__)

ModelType = Literal["lightgbm", "gru", "lstm"]


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
        return float(np.mean(list(predictions.values())))

    total_auc = sum(metrics[m]["mean_auc"] for m in predictions.keys())
    if total_auc == 0:
        logger.warning("Total AUC is 0. Falling back to simple mean.")
        return float(np.mean(list(predictions.values())))

    fusion = sum(
        predictions[m] * metrics[m]["mean_auc"] / total_auc
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
        try:
            lgbm_model = results["lightgbm"]["model"]
            top_features = _extract_feature_importance(lgbm_model, X, top_k=3)
            if top_features:
                feature_importance["lightgbm"] = {"top_features": top_features}
        except Exception as e:
            logger.error(f"Failed to extract feature importance: {e}")

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

    return report


def train_all_models(
    X: pd.DataFrame | None = None,
    y: pd.Series | None = None,
    symbol: str | None = None,
    model_types: List[ModelType] | None = None,
    dl_config: DLConfig | None = None,
) -> Dict[str, Dict]:
    """Train multiple models and return predictions.

    For parallel architecture (Phase D): trains LightGBM and DL models,
    provides multi-dimensional "expert opinions" for CIO Agent.

    Can be called in two ways:
    1. With X, y directly (for testing)
    2. With symbol (for production, calls build_features)

    Args:
        X: Feature matrix (optional, use if not providing symbol)
        y: Target series (optional, use if not providing symbol)
        symbol: Stock ticker (e.g., "AAPL") - alternative to X, y
        model_types: Models to train, default ["lightgbm", "gru"]
        dl_config: DL configuration, default DLConfig()

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

    # Load features
    if X is None or y is None:
        if symbol is None:
            raise ValueError("Must provide either (X, y) or symbol")
        df = build_features(symbol)
        if df.empty:
            raise ValueError(f"No features available for {symbol}")
        X = df[FEATURE_COLS]
        y = df["target_t1"]
    else:
        if X.empty or y.empty:
            raise ValueError("Feature matrix X or target y is empty")

    results = {}

    # Train LightGBM
    if "lightgbm" in model_types:
        logger.info("Training LightGBM")
        try:
            lgbm_model, lgbm_metrics = train_lightgbm(X, y, n_splits=5)
            lgbm_pred = predict_proba_latest(lgbm_model, X)

            results["lightgbm"] = {
                "model": lgbm_model,
                "metrics": lgbm_metrics,
                "prediction": lgbm_pred,
            }
            logger.info(f"LightGBM - AUC: {lgbm_metrics['mean_auc']:.4f}")
        except Exception as e:
            logger.error(f"LightGBM training failed: {e}")

    # Train DL models
    for model_type in ["gru", "lstm"]:
        if model_type not in model_types:
            continue

        logger.info(f"Training {model_type.upper()}")
        try:
            dl_config.model_type = model_type
            # CRITICAL FIX: train_dl_model now returns (model, metrics, scaler)
            dl_model, dl_metrics, dl_scaler = train_dl_model(X, y, config=dl_config)
            # CRITICAL FIX: Pass scaler to predict_proba_latest_dl
            dl_pred = predict_proba_latest_dl(dl_model, X, dl_config, dl_scaler)

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
        lines.append(f"- **预测概率**: {pred:.2%} {'看涨' if pred > 0.5 else '看跌'}")
        lines.append(f"- **模型AUC**: {metrics['mean_auc']:.4f}")
        lines.append(f"- **模型准确率**: {metrics['mean_accuracy']:.4f}")

        if model_name == "lightgbm":
            lines.append("- **分析依据**: 基于截面因子和近期动量")
        elif model_name == "gru":
            seq_len = metrics.get("seq_len", 15)
            lines.append(f"- **分析依据**: 基于过去{seq_len}天的K线序列形态")
        elif model_name == "lstm":
            seq_len = metrics.get("seq_len", 15)
            lines.append(f"- **分析依据**: 基于过去{seq_len}天的长短期记忆模式")

        lines.append("")

    return "\n".join(lines)
