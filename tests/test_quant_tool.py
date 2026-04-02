from __future__ import annotations

import pandas as pd

import app.tools.quant_tool as quant_tool


def test_run_ml_quant_analysis_includes_historical_similarity(monkeypatch):
    panel_df = pd.DataFrame(
        {
            "symbol": pd.Series(["AAPL", "MSFT", "AAPL", "MSFT"], dtype="category"),
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]),
            "close": [100.0, 200.0, 103.0, 198.0],
            "ret_1d": [0.1, 0.0, 0.2, -0.1],
            "ret_3d": [0.1, 0.0, 0.2, -0.1],
            "ret_5d": [0.1, 0.0, 0.2, -0.1],
            "ret_10d": [0.1, 0.0, 0.2, -0.1],
            "volatility_5d": [0.1, 0.2, 0.1, 0.2],
            "volatility_10d": [0.1, 0.2, 0.1, 0.2],
            "volume_ratio_5d": [1.0, 0.9, 1.1, 0.8],
            "gap": [0.0, 0.0, 0.01, -0.01],
            "ma5_vs_ma20": [0.1, 0.0, 0.2, -0.1],
            "rsi_14": [55, 45, 60, 40],
            "n_articles": [1, 0, 2, 1],
            "n_relevant": [1, 0, 2, 1],
            "n_positive": [1, 0, 2, 0],
            "n_negative": [0, 0, 0, 1],
            "n_neutral": [0, 0, 0, 0],
            "sentiment_score": [0.5, 0.0, 0.7, -0.2],
            "relevance_ratio": [1.0, 0.0, 1.0, 1.0],
            "positive_ratio": [1.0, 0.0, 1.0, 0.0],
            "negative_ratio": [0.0, 0.0, 0.0, 1.0],
            "has_news": [1, 0, 1, 1],
            "sentiment_score_3d": [0.5, 0.0, 0.6, -0.1],
            "sentiment_score_5d": [0.5, 0.0, 0.6, -0.1],
            "sentiment_score_10d": [0.5, 0.0, 0.6, -0.1],
            "positive_ratio_3d": [1.0, 0.0, 1.0, 0.0],
            "positive_ratio_5d": [1.0, 0.0, 1.0, 0.0],
            "positive_ratio_10d": [1.0, 0.0, 1.0, 0.0],
            "negative_ratio_3d": [0.0, 0.0, 0.0, 1.0],
            "negative_ratio_5d": [0.0, 0.0, 0.0, 1.0],
            "negative_ratio_10d": [0.0, 0.0, 0.0, 1.0],
            "news_count_3d": [1, 0, 2, 1],
            "news_count_5d": [1, 0, 2, 1],
            "news_count_10d": [1, 0, 2, 1],
            "sentiment_momentum_3d": [0.0, 0.0, 0.0, 0.0],
            "day_of_week": [1, 1, 2, 2],
            "market_sentiment_score": [0.25, 0.25, 0.25, 0.25],
            "market_positive_ratio": [0.5, 0.5, 0.5, 0.5],
            "market_negative_ratio": [0.0, 0.0, 0.5, 0.5],
            "market_news_count_3d": [0.5, 0.5, 1.5, 1.5],
            "market_ret_1d": [0.05, 0.05, 0.05, 0.05],
            "market_volatility_5d": [0.15, 0.15, 0.15, 0.15],
            "market_has_news_ratio": [0.5, 0.5, 1.0, 1.0],
            "sentiment_score_residual": [0.25, -0.25, 0.45, -0.45],
            "news_count_3d_residual": [0.5, -0.5, 0.5, -0.5],
            "ret_1d_residual": [0.05, -0.05, 0.15, -0.15],
            "news_text_blob": ["iphone demand", "macro slowdown", "services growth", "cloud pressure"],
            "target_up_big_move_t3": [1, 0, 1, 0],
        }
    )

    monkeypatch.setattr(quant_tool, "build_panel_features", lambda: panel_df.copy())

    def fake_train_lightgbm_panel_with_text(X, y, trade_dates, text_series, categorical_features=None):
        feature_matrix = X.copy()
        for i in range(10):
            feature_matrix[f"text_svd_{i}"] = 0.0
        return object(), {
            "mean_auc": 0.61,
            "mean_accuracy": 0.56,
            "text_svd_components": 10,
            "per_ticker_auc": {"AAPL": 0.64, "MSFT": 0.58},
            "per_ticker_accuracy": {"AAPL": 0.61, "MSFT": 0.54},
            "per_ticker_eval_rows": {"AAPL": 22, "MSFT": 22},
        }, None, feature_matrix

    monkeypatch.setattr(quant_tool, "train_lightgbm_panel_with_text", fake_train_lightgbm_panel_with_text)
    monkeypatch.setattr(quant_tool, "transform_text_svd_features", lambda text, artifacts: pd.DataFrame(0.0, index=text.index, columns=[f"text_svd_{i}" for i in range(10)]))
    monkeypatch.setattr(quant_tool, "predict_proba_latest", lambda model, X: 0.73)
    monkeypatch.setattr(
        quant_tool,
        "explain_latest_sample",
        lambda model, X: {
            "top_positive": [{"feature": "ret_1d_residual", "value": 0.15, "shap": 0.08}],
            "top_negative": [{"feature": "market_volatility_5d", "value": 0.15, "shap": -0.03}],
        },
    )
    monkeypatch.setattr(
        quant_tool,
        "find_similar_historical_periods",
        lambda history, query, target_col=None: {
            "n_matches": 2,
            "horizon_days": 3,
            "avg_similarity": 0.88,
            "avg_future_return_3d": 0.021,
            "positive_rate": 1.0,
            "target_hit_rate": 0.5,
            "same_symbol_matches": 1,
            "peer_group_matches": 1,
            "market_matches": 0,
            "cross_symbol_matches": 1,
            "strategy": "same_symbol_then_peer_group",
            "matches": [
                {
                    "symbol": "MSFT",
                    "start_date": "2024-01-02",
                    "end_date": "2024-01-03",
                    "similarity": 0.91,
                    "future_return_3d": 0.03,
                    "scope": "peer_group",
                }
            ],
        },
    )

    result = quant_tool._run_ml_quant_analysis_impl("aapl")

    assert result["prediction"] == "up_big_move"
    assert result["final_prediction"] == "up_big_move"
    assert result["final_prob_up"] > result["prob_up"]
    assert result["signal_filter"]["alignment"] == "confirmed"
    assert result["signal_filter"]["position_multiplier"] == 1.25
    assert result["historical_similarity"]["n_matches"] == 2
    assert result["historical_similarity"]["matches"][0]["symbol"] == "MSFT"
    assert result["metrics"]["requested_symbol_auc"] == 0.64
    assert "历史相似阶段" in result["markdown_report"]
    assert "单票外样本表现" in result["markdown_report"]
    assert "最终交易信号" in result["markdown_report"]
    assert "同股票优先、peer group 次优先、全市场兜底" in result["markdown_report"]
