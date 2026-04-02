"""Tests for the LightGBM-only model registry."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import app.ml.model_registry as model_registry
from app.ml.model_registry import format_predictions_for_agent, train_all_models


def _create_mock_features(n_samples: int = 120) -> tuple[pd.DataFrame, pd.Series]:
    np.random.seed(42)
    X = pd.DataFrame(
        {
            "signal_a": np.random.randn(n_samples),
            "signal_b": np.random.randn(n_samples),
            "signal_c": np.random.randn(n_samples),
        }
    )
    y = pd.Series(np.random.randint(0, 2, n_samples))
    return X, y


def test_train_all_models_returns_lightgbm_only():
    X, y = _create_mock_features()

    results = train_all_models(X=X, y=y, model_types=["lightgbm"])

    assert list(results.keys()) == ["lightgbm"]
    result = results["lightgbm"]
    assert "model" in result
    assert "metrics" in result
    assert "prediction" in result
    assert 0.0 <= result["prediction"] <= 1.0


def test_train_all_models_defaults_to_lightgbm():
    X, y = _create_mock_features()

    results = train_all_models(X=X, y=y, model_types=None)

    assert list(results.keys()) == ["lightgbm"]


def test_train_all_models_rejects_removed_models():
    X, y = _create_mock_features()

    with pytest.raises(ValueError, match="Only 'lightgbm' is supported"):
        train_all_models(X=X, y=y, model_types=["gru"])


def test_format_predictions_for_agent():
    results = {
        "lightgbm": {
            "model": object(),
            "metrics": {
                "mean_auc": 0.61,
                "mean_accuracy": 0.56,
                "training_scope": "panel",
                "requested_symbol": "AAPL",
                "requested_symbol_auc": 0.64,
            },
            "prediction": 0.73,
            "signal_filter": {
                "adjusted_probability": 0.7875,
                "alignment": "confirmed",
                "position_multiplier": 1.25,
            },
        }
    }

    markdown = format_predictions_for_agent(results)

    assert "量化模型预测汇总" in markdown
    assert "LIGHTGBM" in markdown
    assert "73.00%" in markdown
    assert "AAPL" in markdown
    assert "0.6400" in markdown
    assert "最终交易信号" in markdown


def test_format_predictions_for_agent_includes_historical_similarity():
    results = {
        "lightgbm": {
            "model": object(),
            "metrics": {
                "mean_auc": 0.61,
                "mean_accuracy": 0.56,
                "training_scope": "panel",
                "requested_symbol": "AAPL",
                "requested_symbol_auc_unavailable": True,
            },
            "prediction": 0.73,
            "signal_filter": {
                "adjusted_probability": 0.615,
                "alignment": "contradicted",
                "position_multiplier": 0.5,
            },
            "historical_similarity": {
                "n_matches": 2,
                "avg_future_return_3d": -0.024,
                "target_hit_rate": 0.5,
                "same_symbol_matches": 1,
                "peer_group_matches": 1,
                "market_matches": 0,
                "matches": [
                    {
                        "symbol": "MSFT",
                    }
                ],
            },
        }
    }

    markdown = format_predictions_for_agent(results)

    assert "历史相似期" in markdown
    assert "MSFT" in markdown
    assert "同股票 1 个、peer group 1 个、全市场补充 0 个" in markdown
    assert "暂不可用" in markdown
    assert "方向冲突" in markdown


def test_train_all_models_symbol_uses_panel_for_lightgbm(monkeypatch):
    panel_df = pd.DataFrame(
        {
            "symbol": pd.Series(["AAPL", "MSFT", "AAPL", "MSFT"], dtype="category"),
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]),
            "close": [100.0, 200.0, 103.0, 198.0],
            "signal": [0.1, -0.1, 0.2, -0.2],
            "news_text_blob": [
                "iphone demand",
                "macro slowdown",
                "services growth",
                "cloud pressure",
            ],
            "target_up_big_move_t3": [1, 0, 1, 0],
        }
    )

    calls: dict[str, object] = {}

    monkeypatch.setattr(model_registry, "build_panel_features", lambda **kwargs: panel_df.copy())
    monkeypatch.setattr(model_registry, "PANEL_FEATURE_COLS", ["symbol", "signal"])

    def fake_train_lightgbm_panel_with_text(
        X,
        y,
        trade_dates,
        text_series,
        categorical_features=None,
        n_splits=5,
    ):
        calls["lightgbm_columns"] = list(X.columns)
        calls["lightgbm_text"] = list(text_series)
        feature_matrix = X.copy()
        feature_matrix["text_svd_0"] = 0.0
        return (
            object(),
            {
                "mean_auc": 0.61,
                "mean_accuracy": 0.56,
                "per_ticker_auc": {"AAPL": 0.63, "MSFT": 0.58},
                "per_ticker_accuracy": {"AAPL": 0.60, "MSFT": 0.55},
                "per_ticker_eval_rows": {"AAPL": 24, "MSFT": 24},
            },
            object(),
            feature_matrix,
        )

    monkeypatch.setattr(
        model_registry, "train_lightgbm_panel_with_text", fake_train_lightgbm_panel_with_text
    )
    monkeypatch.setattr(
        model_registry,
        "transform_text_svd_features",
        lambda text, artifacts: pd.DataFrame({"text_svd_0": [0.0] * len(text)}),
    )
    monkeypatch.setattr(model_registry, "predict_proba_latest", lambda model, X: 0.73)
    monkeypatch.setattr(
        model_registry,
        "find_similar_historical_periods",
        lambda history, query, target_col=None: {
            "n_matches": 2,
            "matches": [{"symbol": "MSFT"}],
        },
    )

    results = train_all_models(symbol="AAPL", model_types=["lightgbm"])

    assert "lightgbm" in results
    assert results["lightgbm"]["prediction"] == 0.73
    assert results["lightgbm"]["metrics"]["training_scope"] == "panel"
    assert results["lightgbm"]["metrics"]["target"] == "target_up_big_move_t3"
    assert results["lightgbm"]["metrics"]["requested_symbol"] == "AAPL"
    assert results["lightgbm"]["metrics"]["requested_symbol_auc"] == 0.63
    assert results["lightgbm"]["metrics"]["requested_symbol_eval_rows"] == 24
    assert calls["lightgbm_text"] == [
        "iphone demand",
        "macro slowdown",
        "services growth",
        "cloud pressure",
    ]
    assert results["lightgbm"]["historical_similarity"]["n_matches"] == 2


def test_train_all_models_symbol_passes_date_range(monkeypatch):
    panel_df = pd.DataFrame(
        {
            "symbol": pd.Series(["AAPL", "MSFT"], dtype="category"),
            "trade_date": pd.to_datetime(["2024-01-03", "2024-01-03"]),
            "close": [103.0, 198.0],
            "signal": [0.2, -0.2],
            "news_text_blob": ["iphone demand", "macro slowdown"],
            "target_up_big_move_t3": [1, 0],
        }
    )

    calls: dict[str, object] = {}

    def fake_build_panel_features(**kwargs):
        calls["panel_kwargs"] = kwargs
        return panel_df.copy()

    monkeypatch.setattr(model_registry, "build_panel_features", fake_build_panel_features)
    monkeypatch.setattr(model_registry, "PANEL_FEATURE_COLS", ["symbol", "signal"])
    monkeypatch.setattr(
        model_registry,
        "train_lightgbm_panel_with_text",
        lambda X, y, trade_dates, text_series, categorical_features=None, n_splits=5: (
            object(),
            {
                "mean_auc": 0.61,
                "mean_accuracy": 0.56,
                "per_ticker_auc": {"AAPL": 0.62},
                "per_ticker_accuracy": {"AAPL": 0.57},
                "per_ticker_eval_rows": {"AAPL": 12},
            },
            object(),
            X.assign(text_svd_0=0.0),
        ),
    )
    monkeypatch.setattr(
        model_registry,
        "transform_text_svd_features",
        lambda text, artifacts: pd.DataFrame({"text_svd_0": [0.0] * len(text)}),
    )
    monkeypatch.setattr(model_registry, "predict_proba_latest", lambda model, X: 0.73)

    results = train_all_models(
        symbol="AAPL",
        model_types=["lightgbm"],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert results["lightgbm"]["metrics"]["training_scope"] == "panel"
    assert calls["panel_kwargs"] == {"start_date": "2024-01-01", "end_date": "2024-01-31"}
    assert results["lightgbm"]["metrics"]["requested_symbol_auc"] == 0.62


def test_format_comparison_markdown_includes_requested_symbol_metrics():
    report = {
        "metadata": {
            "symbol": "AAPL",
            "date_range": ("2024-01-01", "2024-12-31"),
            "generated_at": "2026-04-01 10:30:00",
            "data_points": 252,
        },
        "parameters": {"lightgbm": {"objective": "binary"}},
        "metrics": {
            "lightgbm": {
                "mean_auc": 0.58,
                "mean_accuracy": 0.55,
                "requested_symbol": "AAPL",
                "requested_symbol_auc": 0.62,
                "requested_symbol_accuracy": 0.57,
                "requested_symbol_eval_rows": 48,
            }
        },
        "predictions": {
            "lightgbm": 0.58,
            "fusion_score": 0.60,
            "signal_alignment": "confirmed",
            "position_multiplier": 1.25,
        },
        "feature_importance": {},
        "signal_filter": {
            "alignment": "confirmed",
            "position_multiplier": 1.25,
        },
    }

    markdown = model_registry.format_comparison_markdown(report)

    assert "当前标的 OOS AUC" in markdown
    assert "0.6200" in markdown
    assert "48" in markdown
    assert "建议仓位系数" in markdown


def test_format_comparison_markdown_event_driven_policy_overrides_add_position_language():
    report = {
        "metadata": {
            "symbol": "NVDA",
            "date_range": ("2024-01-01", "2026-04-02"),
            "generated_at": "2026-04-02 20:19:21",
            "data_points": 559,
        },
        "parameters": {"lightgbm": {"objective": "binary"}},
        "metrics": {
            "lightgbm": {
                "mean_auc": 0.5762,
                "mean_accuracy": 0.5751,
                "requested_symbol": "NVDA",
                "requested_symbol_auc": 0.5152,
                "requested_symbol_accuracy": 0.4667,
                "requested_symbol_eval_rows": 465,
            }
        },
        "predictions": {
            "lightgbm": 0.6126,
            "fusion_score": 0.5,
            "signal_alignment": "confirmed",
            "position_multiplier": 0.0,
            "ml_policy": "event_driven_only",
        },
        "feature_importance": {},
        "signal_filter": {
            "alignment": "confirmed",
            "position_multiplier": 0.0,
            "ml_policy": "event_driven_only",
        },
    }

    markdown = model_registry.format_comparison_markdown(report)

    assert "不建议依据 ML 信号加仓" in markdown
    assert "ML 方向性信号已停用" in markdown
