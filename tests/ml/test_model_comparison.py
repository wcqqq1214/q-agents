"""Tests for LightGBM report helpers."""

from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from app.ml.model_registry import (
    _calculate_fusion_score,
    _extract_feature_importance,
    _extract_parameters,
    format_comparison_markdown,
    generate_comparison_report,
)


class TestExtractParameters:
    def test_extract_lightgbm_parameters(self):
        mock_model = Mock()
        mock_model.get_params.return_value = {
            "n_estimators": 200,
            "learning_rate": 0.01,
            "max_depth": 3,
        }

        params = _extract_parameters(mock_model, "lightgbm")

        assert params["n_estimators"] == 200
        assert params["learning_rate"] == 0.01
        assert params["max_depth"] == 3

    def test_extract_parameters_invalid_model_type(self):
        with pytest.raises(ValueError, match="Unknown model type"):
            _extract_parameters(Mock(), "gru")


class TestCalculateFusionScore:
    def test_single_model_returns_own_prediction(self):
        fusion = _calculate_fusion_score(
            {"lightgbm": 0.54},
            {"lightgbm": {"mean_auc": 0.61}},
        )

        assert fusion == 0.54

    def test_fusion_score_fallback_missing_metrics(self):
        fusion = _calculate_fusion_score(
            {"lightgbm": 0.40, "baseline": 0.60},
            {"lightgbm": {"mean_auc": 0.61}},
        )

        assert abs(fusion - 0.5) < 0.001

    def test_fusion_score_fallback_nan_auc(self):
        fusion = _calculate_fusion_score(
            {"lightgbm": 0.40, "baseline": 0.80},
            {"lightgbm": {"mean_auc": float("nan")}, "baseline": {"mean_auc": 0.52}},
        )

        assert abs(fusion - 0.8) < 0.001


class TestExtractFeatureImportance:
    def test_extract_feature_importance_success(self):
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.3, 0.2, 0.4])
        X = pd.DataFrame(
            {"feat_a": [1, 2, 3], "feat_b": [4, 5, 6], "feat_c": [7, 8, 9], "feat_d": [10, 11, 12]}
        )

        importance = _extract_feature_importance(mock_model, X, top_k=2)

        assert len(importance) == 2
        assert importance[0]["name"] == "feat_d"
        assert importance[1]["name"] == "feat_b"

    def test_extract_feature_importance_mismatch(self):
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.2])
        X = pd.DataFrame({"feat_a": [1, 2], "feat_b": [3, 4], "feat_c": [5, 6]})

        assert _extract_feature_importance(mock_model, X) == []


class TestGenerateComparisonReport:
    def test_generate_report_basic(self):
        mock_model = Mock()
        mock_model.get_params.return_value = {"n_estimators": 200}
        mock_model.feature_importances_ = np.array([10, 30, 20])
        results = {
            "lightgbm": {
                "model": mock_model,
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 2.34},
                "prediction": 0.542,
                "feature_matrix": pd.DataFrame(
                    {"symbol": ["AAPL", "MSFT"], "sentiment_score": [0.2, -0.1], "ret_1d_residual": [0.01, -0.02]}
                ),
            }
        }
        X = pd.DataFrame(np.random.randn(100, 3), columns=["a", "b", "c"])

        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=X,
        )

        assert report["metadata"]["symbol"] == "AAPL"
        assert report["metadata"]["data_points"] == 100
        assert report["predictions"]["fusion_score"] == report["predictions"]["lightgbm"]
        assert "feature_importance" in report

    def test_generate_report_empty_x(self):
        with pytest.raises(ValueError, match="Feature matrix X is empty"):
            generate_comparison_report(
                results={"lightgbm": {"model": Mock(), "metrics": {"mean_auc": 0.54}, "prediction": 0.5}},
                symbol="AAPL",
                date_range=("2024-01-01", "2024-12-31"),
                X=pd.DataFrame(),
            )

    def test_generate_report_invalid_date_range_type(self):
        with pytest.raises(ValueError, match="date_range must be tuple"):
            generate_comparison_report(
                results={"lightgbm": {"model": Mock(), "metrics": {"mean_auc": 0.54}, "prediction": 0.5}},
                symbol="AAPL",
                date_range="2024-01-01",
                X=pd.DataFrame(np.random.randn(10, 3)),
            )

    def test_generate_report_includes_historical_similarity(self):
        mock_model = Mock()
        mock_model.get_params.return_value = {"n_estimators": 200}
        mock_model.feature_importances_ = np.array([10, 30])
        results = {
            "lightgbm": {
                "model": mock_model,
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52},
                "prediction": 0.542,
                "feature_matrix": pd.DataFrame({"symbol": ["AAPL"], "ret_1d": [0.1]}),
                "historical_similarity": {
                    "n_matches": 2,
                    "horizon_days": 3,
                    "avg_similarity": 0.91,
                    "avg_future_return_3d": 0.032,
                    "positive_rate": 1.0,
                    "target_hit_rate": 0.5,
                    "same_symbol_matches": 1,
                    "peer_group_matches": 1,
                    "market_matches": 0,
                    "matches": [
                        {
                            "symbol": "MSFT",
                            "start_date": "2024-01-04",
                            "end_date": "2024-01-08",
                            "similarity": 0.93,
                            "future_return_3d": 0.05,
                            "scope": "peer_group",
                        }
                    ],
                },
            }
        }

        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=pd.DataFrame({"different": [1, 2]}),
        )

        assert report["historical_similarity"]["n_matches"] == 2
        assert report["historical_similarity"]["matches"][0]["symbol"] == "MSFT"
        assert report["predictions"]["fusion_score"] > report["predictions"]["lightgbm"]
        assert report["predictions"]["signal_alignment"] == "confirmed"
        assert report["predictions"]["position_multiplier"] == 1.25


class TestFormatComparisonMarkdown:
    def test_markdown_contains_sections(self):
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {"lightgbm": {"objective": "binary", "learning_rate": 0.01}},
            "metrics": {"lightgbm": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 2.34}},
            "predictions": {"lightgbm": 0.542, "fusion_score": 0.542},
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        assert "# LightGBM 面板模型报告" in markdown
        assert "## 模型参数" in markdown
        assert "## 性能指标" in markdown
        assert "## 最新预测信号" in markdown
        assert "## 综合评估" in markdown
        assert "AAPL" in markdown
        assert "GRU" not in markdown

    def test_markdown_missing_metadata_raises(self):
        with pytest.raises(ValueError, match="missing 'metadata'"):
            format_comparison_markdown({})

    def test_markdown_missing_parameters_raises(self):
        with pytest.raises(ValueError, match="missing 'parameters'"):
            format_comparison_markdown({"metadata": {"symbol": "AAPL"}})

    def test_markdown_missing_metrics_raises(self):
        report = {
            "metadata": {"symbol": "AAPL"},
            "parameters": {},
            "predictions": {},
            "feature_importance": {},
        }

        with pytest.raises(ValueError, match="missing 'metrics'"):
            format_comparison_markdown(report)

    def test_markdown_with_feature_importance_and_similarity(self):
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {"lightgbm": {}},
            "metrics": {"lightgbm": {"mean_auc": 0.54, "mean_accuracy": 0.52}},
            "predictions": {"lightgbm": 0.5, "fusion_score": 0.5},
            "feature_importance": {
                "lightgbm": {
                    "top_features": [
                        {"name": "RSI_14", "importance": 100},
                        {"name": "Volume_Ratio", "importance": 80},
                    ]
                }
            },
            "historical_similarity": {
                "n_matches": 2,
                "horizon_days": 3,
                "avg_similarity": 0.91,
                "avg_future_return_3d": 0.032,
                "positive_rate": 1.0,
                "target_hit_rate": 0.5,
                "same_symbol_matches": 1,
                "peer_group_matches": 1,
                "market_matches": 0,
                "matches": [
                    {
                        "symbol": "MSFT",
                        "start_date": "2024-01-04",
                        "end_date": "2024-01-08",
                        "similarity": 0.93,
                        "future_return_3d": 0.05,
                        "scope": "peer_group",
                    }
                ],
            },
        }

        markdown = format_comparison_markdown(report)

        assert "## LightGBM 特征重要性" in markdown
        assert "RSI_14" in markdown
        assert "## 历史相似阶段" in markdown
        assert "MSFT" in markdown
