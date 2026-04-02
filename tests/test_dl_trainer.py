"""Tests for deep learning trainer module with TimeSeriesSplit and early stopping."""

import numpy as np
import pandas as pd
import pytest

from app.ml.dl_config import DLConfig
from app.ml.dl_trainer import train_dl_model


def test_train_dl_model_returns_model_and_metrics():
    """Test train_dl_model returns model and metrics in correct format"""
    # Create mock data with proper column names
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
    X = pd.DataFrame(np.random.randn(1000, len(columns)), columns=columns)
    y = pd.Series(np.random.randint(0, 2, 1000))

    config = DLConfig(
        model_type="gru",
        seq_len=15,
        max_epochs=5,  # Short for testing
        n_splits=2,  # Fewer splits for speed
    )

    model, metrics, scaler = train_dl_model(X, y, config=config)

    # Check model is returned
    assert model is not None

    # Check scaler is returned
    assert scaler is not None

    # Check metrics format (compatible with LightGBM)
    assert "mean_auc" in metrics
    assert "mean_accuracy" in metrics
    assert "fold_aucs" in metrics
    assert "fold_accuracies" in metrics
    assert "train_test_split" in metrics
    assert "model_type" in metrics
    assert "seq_len" in metrics

    # Backward compatibility keys
    assert "auc" in metrics
    assert "accuracy" in metrics

    # Training time tracking
    assert "training_time_seconds" in metrics
    assert isinstance(metrics["training_time_seconds"], float)
    assert metrics["training_time_seconds"] > 0


def test_train_dl_model_empty_data():
    """Test train_dl_model raises error on empty data"""
    X = pd.DataFrame()
    y = pd.Series()
    config = DLConfig()

    with pytest.raises(ValueError, match="empty"):
        train_dl_model(X, y, config)


def test_train_dl_model_mismatched_lengths():
    """Test train_dl_model raises error on mismatched X and y"""
    X = pd.DataFrame(np.random.randn(100, 10))
    y = pd.Series(np.random.randint(0, 2, 50))
    config = DLConfig()

    with pytest.raises(ValueError, match="same number of rows"):
        train_dl_model(X, y, config)


def test_train_dl_model_rejects_nan_features():
    """Test train_dl_model raises a clear error when X contains NaNs."""
    X = pd.DataFrame(
        {
            "ret_1d": [0.1] * 30,
            "ret_3d": [0.1] * 30,
            "ret_5d": [0.1] * 30,
            "ret_10d": [0.1] * 30,
            "volatility_5d": [0.1] * 30,
            "volatility_10d": [0.1] * 30,
            "volume_ratio_5d": [0.1] * 30,
            "gap": [0.1] * 30,
            "ma5_vs_ma20": [0.1] * 30,
            "rsi_14": [50.0] * 30,
            "n_articles": [1.0] * 30,
            "n_relevant": [1.0] * 30,
            "n_positive": [1.0] * 30,
            "n_negative": [0.0] * 30,
            "news_count_3d": [1.0] * 30,
            "news_count_5d": [1.0] * 30,
            "news_count_10d": [1.0] * 30,
            "day_of_week": [1.0] * 30,
            "has_news": [1.0] * 30,
            "n_neutral": [0.0] * 30,
            "sentiment_score": [0.2] * 30,
            "relevance_ratio": [1.0] * 30,
            "positive_ratio": [1.0] * 30,
            "negative_ratio": [0.0] * 30,
            "sentiment_score_3d": [0.2] * 30,
            "sentiment_score_5d": [0.2] * 30,
            "sentiment_score_10d": [0.2] * 30,
            "sentiment_momentum_3d": [0.0] * 30,
        }
    )
    X.loc[0, "ma5_vs_ma20"] = np.nan
    y = pd.Series(([0, 1] * 15))

    with pytest.raises(ValueError, match="contains NaN"):
        train_dl_model(X, y, DLConfig(max_epochs=2, n_splits=2))
