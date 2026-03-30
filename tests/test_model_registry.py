"""Tests for model registry module with multi-model orchestration."""

import numpy as np
import pandas as pd
import pytest

from app.ml.dl_config import DLConfig
from app.ml.model_registry import (
    format_predictions_for_agent,
    predict_proba_latest_dl,
    train_all_models,
)


def _create_mock_features(n_samples: int = 1000) -> tuple[pd.DataFrame, pd.Series]:
    """Create mock feature matrix and target for testing."""
    np.random.seed(42)
    columns = [
        "ret_1d", "ret_3d", "ret_5d", "ret_10d",
        "volatility_5d", "volatility_10d", "volume_ratio_5d",
        "gap", "ma5_vs_ma20", "rsi_14",
        "n_articles", "n_relevant", "n_positive", "n_negative",
        "news_count_3d", "news_count_5d", "news_count_10d",
        "day_of_week", "has_news", "n_neutral",
        "sentiment_score", "relevance_ratio", "positive_ratio", "negative_ratio",
        "sentiment_score_3d", "sentiment_score_5d", "sentiment_score_10d",
        "sentiment_momentum_3d",
    ]
    X = pd.DataFrame(np.random.randn(n_samples, len(columns)), columns=columns)
    y = pd.Series(np.random.randint(0, 2, n_samples))
    return X, y


def test_train_all_models_returns_multiple_models():
    """Test train_all_models returns results for multiple models"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    # Test with both LightGBM and GRU
    results = train_all_models(
        X=X,
        y=y,
        model_types=["lightgbm", "gru"],
        dl_config=config,
    )

    # Check that results contain both models
    assert "lightgbm" in results
    assert "gru" in results

    # Check structure of each result
    for model_name, result in results.items():
        assert "model" in result
        assert "metrics" in result
        assert "prediction" in result

        # Check metrics format
        metrics = result["metrics"]
        assert "mean_auc" in metrics
        assert "mean_accuracy" in metrics

        # Check prediction is a float between 0 and 1
        pred = result["prediction"]
        assert isinstance(pred, float)
        assert 0.0 <= pred <= 1.0

        # DL models should have scaler
        if model_name in ["gru", "lstm"]:
            assert "scaler" in result


def test_train_all_models_lightgbm_only():
    """Test train_all_models with only LightGBM"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    results = train_all_models(
        X=X,
        y=y,
        model_types=["lightgbm"],
        dl_config=config,
    )

    assert "lightgbm" in results
    assert "gru" not in results
    assert "lstm" not in results


def test_train_all_models_gru_only():
    """Test train_all_models with only GRU"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    results = train_all_models(
        X=X,
        y=y,
        model_types=["gru"],
        dl_config=config,
    )

    assert "gru" in results
    assert "lightgbm" not in results


def test_train_all_models_default_models():
    """Test train_all_models uses default models when not specified"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    results = train_all_models(
        X=X,
        y=y,
        model_types=None,  # Should default to ["lightgbm", "gru"]
        dl_config=config,
    )

    # Default should include both
    assert "lightgbm" in results or "gru" in results


def test_predict_proba_latest_dl_with_scaler():
    """Test predict_proba_latest_dl uses provided scaler correctly"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    # Train to get model and scaler
    results = train_all_models(
        X=X,
        y=y,
        model_types=["gru"],
        dl_config=config,
    )

    gru_result = results["gru"]
    model = gru_result["model"]
    scaler = gru_result["scaler"]

    # Make prediction with scaler
    pred = predict_proba_latest_dl(model, X, config, scaler)

    assert isinstance(pred, float)
    assert 0.0 <= pred <= 1.0


def test_predict_proba_latest_dl_insufficient_data():
    """Test predict_proba_latest_dl raises error on insufficient data"""
    from sklearn.preprocessing import RobustScaler

    X = pd.DataFrame(np.random.randn(5, 10))  # Too small
    config = DLConfig(seq_len=15)

    # Create a dummy model
    import torch
    model = torch.nn.Linear(10, 1)
    scaler = RobustScaler()

    with pytest.raises(ValueError, match="Insufficient data"):
        predict_proba_latest_dl(model, X, config, scaler)


def test_format_predictions_for_agent():
    """Test format_predictions_for_agent produces valid markdown"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    results = train_all_models(
        X=X,
        y=y,
        model_types=["lightgbm", "gru"],
        dl_config=config,
    )

    markdown = format_predictions_for_agent(results)

    # Check markdown structure
    assert isinstance(markdown, str)
    assert "量化模型预测汇总" in markdown
    assert "LIGHTGBM" in markdown or "lightgbm" in markdown.lower()
    assert "GRU" in markdown or "gru" in markdown.lower()

    # Check for prediction probabilities
    assert "%" in markdown  # Should have percentage format


def test_format_predictions_for_agent_single_model():
    """Test format_predictions_for_agent with single model"""
    X, y = _create_mock_features(n_samples=1000)

    config = DLConfig(max_epochs=3, n_splits=2)

    results = train_all_models(
        X=X,
        y=y,
        model_types=["lightgbm"],
        dl_config=config,
    )

    markdown = format_predictions_for_agent(results)

    assert isinstance(markdown, str)
    assert "量化模型预测汇总" in markdown
    assert "LIGHTGBM" in markdown or "lightgbm" in markdown.lower()
