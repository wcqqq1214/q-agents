"""Tests for model comparison functions."""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock

from app.ml.model_registry import (
    _extract_parameters,
    _calculate_fusion_score,
    _extract_feature_importance,
    generate_comparison_report,
    format_comparison_markdown,
)
from app.ml.dl_config import DLConfig


class TestExtractParameters:
    """Test parameter extraction for heterogeneous models."""

    def test_extract_lightgbm_parameters(self):
        """Test LightGBM parameter extraction."""
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

    def test_extract_gru_parameters(self):
        """Test GRU parameter extraction from DLConfig."""
        dl_config = DLConfig()
        dl_config.hidden_size = 32
        dl_config.num_layers = 1
        dl_config.dropout = 0.4
        dl_config.seq_len = 15

        mock_model = Mock()
        params = _extract_parameters(mock_model, "gru", dl_config)

        assert params["hidden_size"] == 32
        assert params["num_layers"] == 1
        assert params["dropout"] == 0.4
        assert params["seq_len"] == 15

    def test_extract_lstm_parameters(self):
        """Test LSTM parameter extraction from DLConfig."""
        dl_config = DLConfig()
        dl_config.hidden_size = 64
        dl_config.num_layers = 2
        dl_config.dropout = 0.3
        dl_config.seq_len = 20

        mock_model = Mock()
        params = _extract_parameters(mock_model, "lstm", dl_config)

        assert params["hidden_size"] == 64
        assert params["num_layers"] == 2
        assert params["dropout"] == 0.3
        assert params["seq_len"] == 20

    def test_extract_parameters_invalid_model_type(self):
        """Test error handling for invalid model type."""
        mock_model = Mock()

        with pytest.raises(ValueError, match="Unknown model type"):
            _extract_parameters(mock_model, "invalid_model")

    def test_extract_pytorch_without_config(self):
        """Test error when DLConfig not provided for PyTorch models."""
        mock_model = Mock()

        with pytest.raises(ValueError, match="DLConfig required for gru"):
            _extract_parameters(mock_model, "gru", dl_config=None)

    def test_extract_lstm_without_config(self):
        """Test error when DLConfig not provided for LSTM model."""
        mock_model = Mock()

        with pytest.raises(ValueError, match="DLConfig required for lstm"):
            _extract_parameters(mock_model, "lstm", dl_config=None)


class TestCalculateFusionScore:
    """Test fusion score calculation."""

    def test_fusion_score_equal_weights(self):
        """Test fusion score with equal AUC weights."""
        predictions = {
            "lightgbm": 0.54,
            "gru": 0.52,
            "lstm": 0.51,
        }
        metrics = {
            "lightgbm": {"mean_auc": 0.54},
            "gru": {"mean_auc": 0.54},
            "lstm": {"mean_auc": 0.54},
        }

        fusion = _calculate_fusion_score(predictions, metrics)

        # With equal weights, should be simple average
        expected = (0.54 + 0.52 + 0.51) / 3
        assert abs(fusion - expected) < 0.001

    def test_fusion_score_weighted(self):
        """Test fusion score with different AUC weights."""
        predictions = {
            "lightgbm": 0.60,
            "gru": 0.50,
            "lstm": 0.50,
        }
        metrics = {
            "lightgbm": {"mean_auc": 0.60},  # Higher weight
            "gru": {"mean_auc": 0.50},
            "lstm": {"mean_auc": 0.50},
        }

        fusion = _calculate_fusion_score(predictions, metrics)

        # LightGBM should have more influence
        assert fusion > 0.53  # Closer to 0.60 than simple average

    def test_fusion_score_fallback_zero_auc(self):
        """Test fallback when all AUC are zero."""
        predictions = {
            "lightgbm": 0.50,
            "gru": 0.60,
            "lstm": 0.70,
        }
        metrics = {
            "lightgbm": {"mean_auc": 0.0},
            "gru": {"mean_auc": 0.0},
            "lstm": {"mean_auc": 0.0},
        }

        fusion = _calculate_fusion_score(predictions, metrics)

        # Should fall back to simple mean
        expected = (0.50 + 0.60 + 0.70) / 3
        assert abs(fusion - expected) < 0.001

    def test_fusion_score_missing_metrics(self):
        """Test fallback when metrics missing for some models."""
        predictions = {
            "lightgbm": 0.50,
            "gru": 0.60,
        }
        metrics = {
            "lightgbm": {"mean_auc": 0.5},
            # gru missing
        }

        fusion = _calculate_fusion_score(predictions, metrics)

        # Should use simple mean fallback
        expected = (0.50 + 0.60) / 2
        assert abs(fusion - expected) < 0.001

    def test_fusion_score_fallback_nan_auc(self):
        """Test fallback when any AUC is NaN."""
        predictions = {
            "lightgbm": 0.40,
            "gru": 0.60,
            "lstm": 0.80,
        }
        metrics = {
            "lightgbm": {"mean_auc": 0.55},
            "gru": {"mean_auc": float("nan")},
            "lstm": {"mean_auc": 0.52},
        }

        fusion = _calculate_fusion_score(predictions, metrics)

        expected = (0.40 + 0.60 + 0.80) / 3
        assert abs(fusion - expected) < 0.001


class TestExtractFeatureImportance:
    """Test feature importance extraction."""

    def test_extract_feature_importance_success(self):
        """Test successful feature importance extraction."""
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.3, 0.2, 0.4])

        # Create DataFrame with feature names
        X = pd.DataFrame(
            {"feat_a": [1, 2, 3], "feat_b": [4, 5, 6], "feat_c": [7, 8, 9], "feat_d": [10, 11, 12]}
        )

        importance = _extract_feature_importance(mock_model, X, top_k=2)

        assert len(importance) == 2
        assert importance[0]["name"] == "feat_d"  # Highest
        assert importance[0]["importance"] == 0.4
        assert importance[1]["name"] == "feat_b"  # Second highest
        assert importance[1]["importance"] == 0.3

    def test_extract_feature_importance_top_3(self):
        """Test extraction of top 3 features."""
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.3, 0.2, 0.4, 0.05])

        X = pd.DataFrame(
            {
                "RSI_14": [1, 2, 3],
                "Volume_Ratio": [4, 5, 6],
                "MACD_Signal": [7, 8, 9],
                "SMA_20": [10, 11, 12],
                "Bollinger_Upper": [13, 14, 15],
            }
        )

        importance = _extract_feature_importance(mock_model, X, top_k=3)

        assert len(importance) == 3
        # Top 3: SMA_20 (0.4), Volume_Ratio (0.3), MACD_Signal (0.2)
        assert importance[0]["name"] == "SMA_20"
        assert importance[0]["importance"] == 0.4

    def test_extract_feature_importance_no_features(self):
        """Test handling when no features available (empty importances)."""
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([])

        X = pd.DataFrame(columns=[])

        importance = _extract_feature_importance(mock_model, X)

        assert importance == []

    def test_extract_feature_importance_empty_x(self):
        """Test handling when X DataFrame is empty."""
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.2, 0.3])

        X = pd.DataFrame()

        importance = _extract_feature_importance(mock_model, X)

        assert importance == []

    def test_extract_feature_importance_mismatch(self):
        """Test handling when feature count mismatch."""
        mock_model = Mock()
        mock_model.feature_importances_ = np.array([0.1, 0.2])  # Only 2

        X = pd.DataFrame({"feat_a": [1, 2], "feat_b": [3, 4], "feat_c": [5, 6]})  # 3 columns

        importance = _extract_feature_importance(mock_model, X)

        assert importance == []


class TestGenerateComparisonReport:
    """Test report generation."""

    def test_generate_report_basic(self):
        """Test basic report generation."""
        # Create mock results
        results = {
            "lightgbm": {
                "model": Mock(get_params=Mock(return_value={"n_estimators": 200})),
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 2.34},
                "prediction": 0.542,
            },
            "gru": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.55, "mean_accuracy": 0.53, "training_time": 45.67},
                "prediction": 0.518,
            },
        }

        X = pd.DataFrame(np.random.randn(100, 10))
        dl_config = DLConfig()

        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=X,
            dl_config=dl_config,
        )

        # Check structure
        assert "metadata" in report
        assert "parameters" in report
        assert "metrics" in report
        assert "predictions" in report

        # Check metadata
        assert report["metadata"]["symbol"] == "AAPL"
        assert report["metadata"]["date_range"] == ("2024-01-01", "2024-12-31")
        assert report["metadata"]["data_points"] == 100

        # Check predictions include fusion score
        assert "fusion_score" in report["predictions"]
        assert 0 <= report["predictions"]["fusion_score"] <= 1

    def test_generate_report_empty_x(self):
        """Test ValueError when X is empty."""
        results = {
            "lightgbm": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.54},
                "prediction": 0.5,
            }
        }

        X = pd.DataFrame()

        with pytest.raises(ValueError, match="Feature matrix X is empty"):
            generate_comparison_report(
                results=results,
                symbol="AAPL",
                date_range=("2024-01-01", "2024-12-31"),
                X=X,
                dl_config=DLConfig(),
            )

    def test_generate_report_invalid_date_range_type(self):
        """Test ValueError when date_range is not a tuple."""
        results = {
            "lightgbm": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.54},
                "prediction": 0.5,
            }
        }

        X = pd.DataFrame(np.random.randn(10, 5))

        with pytest.raises(ValueError, match="date_range must be tuple"):
            generate_comparison_report(
                results=results,
                symbol="AAPL",
                date_range="2024-01-01",  # Not a tuple
                X=X,
                dl_config=DLConfig(),
            )

    def test_generate_report_invalid_date_range_elements(self):
        """Test ValueError when date_range elements are not strings."""
        results = {
            "lightgbm": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.54},
                "prediction": 0.5,
            }
        }

        X = pd.DataFrame(np.random.randn(10, 5))

        # Note: The tuple validation catches this first before checking element types
        with pytest.raises(ValueError, match="date_range must be tuple"):
            generate_comparison_report(
                results=results,
                symbol="AAPL",
                date_range=(2024, 1, 1),  # Not strings, but tuple of wrong length
                X=X,
                dl_config=DLConfig(),
            )

    def test_generate_report_with_lstm(self):
        """Test report generation with all three models."""
        results = {
            "lightgbm": {
                "model": Mock(get_params=Mock(return_value={"n_estimators": 200})),
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52},
                "prediction": 0.542,
            },
            "gru": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.55, "mean_accuracy": 0.53},
                "prediction": 0.518,
            },
            "lstm": {
                "model": Mock(),
                "metrics": {"mean_auc": 0.53, "mean_accuracy": 0.51},
                "prediction": 0.521,
            },
        }

        X = pd.DataFrame(np.random.randn(100, 10))
        dl_config = DLConfig()

        report = generate_comparison_report(
            results=results,
            symbol="NVDA",
            date_range=("2024-01-01", "2024-06-30"),
            X=X,
            dl_config=dl_config,
        )

        assert report["metadata"]["symbol"] == "NVDA"
        assert "lstm" in report["predictions"]
        assert "fusion_score" in report["predictions"]

    def test_generate_report_with_feature_importance(self):
        """Test report includes feature importance from LightGBM."""
        mock_model = Mock()
        mock_model.get_params.return_value = {"n_estimators": 200}
        mock_model.feature_importances_ = np.array([10, 30, 20, 40])

        results = {
            "lightgbm": {
                "model": mock_model,
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52},
                "prediction": 0.542,
            }
        }

        X = pd.DataFrame(
            {"RSI_14": [1, 2], "Volume_Ratio": [3, 4], "MACD_Signal": [5, 6], "SMA_20": [7, 8]}
        )
        dl_config = DLConfig()

        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=X,
            dl_config=dl_config,
        )

        assert "feature_importance" in report
        assert "lightgbm" in report["feature_importance"]
        assert "top_features" in report["feature_importance"]["lightgbm"]

    def test_generate_report_prefers_lightgbm_feature_matrix_from_results(self):
        """Test feature importance uses the LightGBM-specific feature matrix when provided."""
        mock_model = Mock()
        mock_model.get_params.return_value = {"n_estimators": 200}
        mock_model.feature_importances_ = np.array([10, 30, 20])

        results = {
            "lightgbm": {
                "model": mock_model,
                "metrics": {"mean_auc": 0.54, "mean_accuracy": 0.52},
                "prediction": 0.542,
                "feature_matrix": pd.DataFrame(
                    {
                        "symbol": ["AAPL", "MSFT"],
                        "sentiment_score": [0.2, -0.1],
                        "ret_1d_residual": [0.01, -0.02],
                    }
                ),
            }
        }

        X = pd.DataFrame({"different": [1, 2]})
        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=X,
            dl_config=DLConfig(),
        )

        top_names = [item["name"] for item in report["feature_importance"]["lightgbm"]["top_features"]]
        assert "symbol" in top_names
        assert "sentiment_score" in top_names

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
                    "cross_symbol_matches": 1,
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

        X = pd.DataFrame({"different": [1, 2]})
        report = generate_comparison_report(
            results=results,
            symbol="AAPL",
            date_range=("2024-01-01", "2024-12-31"),
            X=X,
            dl_config=DLConfig(),
        )

        assert "historical_similarity" in report
        assert report["historical_similarity"]["n_matches"] == 2
        assert report["historical_similarity"]["matches"][0]["symbol"] == "MSFT"


class TestFormatComparisonMarkdown:
    """Test markdown formatting."""

    def test_markdown_contains_sections(self):
        """Test markdown output contains all required sections."""
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {
                "lightgbm": {"n_estimators": 200, "learning_rate": 0.01},
                "gru": {"hidden_size": 32, "num_layers": 1},
                "lstm": {"hidden_size": 64, "num_layers": 2},
            },
            "metrics": {
                "lightgbm": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 2.34},
                "gru": {"mean_auc": 0.55, "mean_accuracy": 0.53, "training_time": 45.67},
                "lstm": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 52.11},
            },
            "predictions": {
                "lightgbm": 0.542,
                "gru": 0.518,
                "lstm": 0.521,
                "fusion_score": 0.527,
            },
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        # Check for key sections
        assert "# 量化预测模型对比报告" in markdown
        assert "## 模型参数对比" in markdown
        assert "## 性能指标" in markdown
        assert "## 最新预测信号" in markdown
        assert "## 综合评估" in markdown

        # Check for data
        assert "AAPL" in markdown

    def test_markdown_header_format(self):
        """Test markdown header format."""
        report = {
            "metadata": {
                "symbol": "TSLA",
                "date_range": ("2024-01-01", "2024-03-31"),
                "generated_at": "2026-04-01 12:00:00",
                "data_points": 60,
            },
            "parameters": {},
            "metrics": {},
            "predictions": {},
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        # Check header
        assert markdown.startswith("# 量化预测模型对比报告")
        assert "TSLA" in markdown
        assert "2024-01-01" in markdown or "2024-01-01 至" in markdown

    def test_markdown_metrics_formatted(self):
        """Test metrics are formatted correctly."""
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.5432, "mean_accuracy": 0.5211, "training_time": 2.5},
                "gru": {"mean_auc": 0.5511, "mean_accuracy": 0.5312, "training_time": 45.7},
                "lstm": {"mean_auc": 0.5399, "mean_accuracy": 0.5188, "training_time": 52.3},
            },
            "predictions": {
                "lightgbm": 0.542,
                "gru": 0.518,
                "fusion_score": 0.527,
            },
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        # Check that metrics are in the markdown
        assert "Mean AUC" in markdown
        assert "0.5432" in markdown or "0.543" in markdown  # Formatted to 4 decimal places

    def test_markdown_predictions_section(self):
        """Test predictions section with signals."""
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.54, "mean_accuracy": 0.52},
                "gru": {"mean_auc": 0.55, "mean_accuracy": 0.53},
                "lstm": {"mean_auc": 0.53, "mean_accuracy": 0.51},
            },
            "predictions": {
                "lightgbm": 0.54,  # Above 0.5, should be "看涨"
                "gru": 0.48,  # Below 0.5, should be "看跌"
                "lstm": 0.51,  # Above 0.5, should be "看涨"
                "fusion_score": 0.51,
            },
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        # Check predictions section exists
        assert "## 最新预测信号" in markdown

        # Check signal labels (看涨/看跌)
        assert "看涨" in markdown or "看跌" in markdown

    def test_markdown_missing_metadata_raises(self):
        """Test ValueError when metadata missing."""
        with pytest.raises(ValueError, match="missing 'metadata'"):
            format_comparison_markdown({})

    def test_markdown_missing_parameters_raises(self):
        """Test ValueError when parameters missing."""
        with pytest.raises(ValueError, match="missing 'parameters'"):
            format_comparison_markdown({"metadata": {"symbol": "AAPL"}})

    def test_markdown_missing_metrics_raises(self):
        """Test ValueError when metrics missing from report (not just empty)."""
        # Note: The function checks for key existence, not empty dict
        # So we need to test with metrics key actually missing
        report = {
            "metadata": {"symbol": "AAPL"},
            "parameters": {},
            # metrics key is completely missing
            "predictions": {},
            "feature_importance": {},
        }

        with pytest.raises(ValueError, match="missing 'metrics'"):
            format_comparison_markdown(report)

    def test_markdown_fusion_algorithm_explanation(self):
        """Test fusion algorithm explanation is included."""
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.54},
                "gru": {"mean_auc": 0.55},
            },
            "predictions": {
                "lightgbm": 0.5,
                "gru": 0.5,
                "fusion_score": 0.5,
            },
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        # Check fusion explanation
        assert "融合算法" in markdown
        assert "AUC" in markdown

    def test_markdown_with_feature_importance(self):
        """Test markdown includes feature importance section."""
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.54},
            },
            "predictions": {
                "lightgbm": 0.5,
                "fusion_score": 0.5,
            },
            "feature_importance": {
                "lightgbm": {
                    "top_features": [
                        {"name": "RSI_14", "importance": 100},
                        {"name": "Volume_Ratio", "importance": 80},
                        {"name": "MACD_Signal", "importance": 60},
                    ]
                }
            },
        }

        markdown = format_comparison_markdown(report)

        # Check feature importance section
        assert "## LightGBM 特征重要性" in markdown
        assert "RSI_14" in markdown
        assert "Volume_Ratio" in markdown

    def test_markdown_with_historical_similarity(self):
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.54},
            },
            "predictions": {
                "lightgbm": 0.5,
                "fusion_score": 0.5,
            },
            "feature_importance": {},
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
                "cross_symbol_matches": 1,
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

        assert "## 历史相似阶段" in markdown
        assert "平均相似度约" in markdown
        assert "MSFT" in markdown
        assert "同股票优先、peer group 次优先、全市场兜底" in markdown

    def test_markdown_formats_nan_metrics_as_na(self):
        report = {
            "metadata": {
                "symbol": "AAPL",
                "date_range": ("2024-01-01", "2024-12-31"),
                "generated_at": "2026-04-01 10:30:00",
                "data_points": 252,
            },
            "parameters": {},
            "metrics": {
                "lightgbm": {"mean_auc": 0.54, "mean_accuracy": 0.52, "training_time": 2.3},
                "gru": {"mean_auc": float("nan"), "mean_accuracy": 0.51, "training_time": 10.0},
            },
            "predictions": {
                "lightgbm": 0.54,
                "gru": 0.48,
                "fusion_score": float("nan"),
            },
            "feature_importance": {},
        }

        markdown = format_comparison_markdown(report)

        assert "| Mean AUC | 0.5400 | N/A | N/A |" in markdown
        assert "| **融合信号** | **N/A** | **N/A** |" in markdown
