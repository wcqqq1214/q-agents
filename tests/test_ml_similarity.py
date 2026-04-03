from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.shap_explainer import build_markdown_report
from app.ml.similarity import find_similar_historical_periods


def test_find_similar_historical_periods_returns_expected_match():
    dates = pd.bdate_range("2024-01-01", periods=10)
    rows = []

    aapl_signal = [0, 0, 0, 0, 0, 0, 7, 8, 9, 10]
    msft_signal = [0, 0, 0, 8, 9, 10, 0, 0, 0, 0]
    aapl_close = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    msft_close = [100, 100, 100, 100, 100, 100, 103, 104, 105, 106]

    for date, signal, close in zip(dates, aapl_signal, aapl_close, strict=False):
        rows.append(
            {
                "symbol": "AAPL",
                "trade_date": date,
                "close": close,
                "signal": float(signal),
                "momentum": 1.0 if signal >= 7 else 0.0,
                "target_up_big_move_t3": np.nan,
            }
        )

    for idx, (date, signal, close) in enumerate(zip(dates, msft_signal, msft_close, strict=False)):
        target_hit = 1.0 if idx == 5 else np.nan
        rows.append(
            {
                "symbol": "MSFT",
                "trade_date": date,
                "close": close,
                "signal": float(signal),
                "momentum": 1.0 if signal >= 8 else 0.0,
                "target_up_big_move_t3": target_hit,
            }
        )

    frame = pd.DataFrame(rows)
    query = frame.loc[frame["symbol"] == "AAPL"].copy()

    history = frame.loc[frame["symbol"] == "MSFT"].copy()

    summary = find_similar_historical_periods(
        history,
        query,
        feature_columns=["signal", "momentum"],
        window_size=3,
        top_k=1,
        future_horizon_days=3,
    )

    assert summary["n_matches"] == 1
    assert summary["query_symbol"] == "AAPL"
    assert summary["matches"][0]["symbol"] == "MSFT"
    assert summary["matches"][0]["end_date"] == "2024-01-08"
    assert np.isclose(summary["avg_future_return_3d"], 0.05)
    assert summary["positive_rate"] == 1.0
    assert summary["target_hit_rate"] == 1.0
    assert summary["same_symbol_matches"] == 0
    assert summary["cross_symbol_matches"] == 1
    assert summary["strategy"] == "market_only"
    assert summary["matches"][0]["scope"] == "market"


def test_find_similar_historical_periods_prioritizes_same_symbol_then_peer_group_then_market():
    dates = pd.bdate_range("2024-01-01", periods=8)
    peer_dates = dates[:-1]
    rows = []

    msft_signal = [1, 1, 1, 4, 4, 7, 8, 9]
    amzn_signal = [0, 0, 0, 7, 8, 9, 0]
    tsla_signal = [0, 0, 0, 6, 7, 8, 0, 0]
    msft_close = [100, 101, 102, 103, 104, 105, 106, 107]
    amzn_close = [100, 100, 100, 103, 104, 105, 106]
    tsla_close = [100, 100, 100, 102, 103, 104, 104, 104]

    for idx, (date, signal, close) in enumerate(zip(dates, msft_signal, msft_close, strict=False)):
        rows.append(
            {
                "symbol": "MSFT",
                "trade_date": date,
                "close": close,
                "signal": float(signal),
                "momentum": float(signal) / 10.0,
                "target_up_big_move_t3": 1.0 if idx == 5 else np.nan,
            }
        )

    for idx, (date, signal, close) in enumerate(
        zip(peer_dates, amzn_signal, amzn_close, strict=False)
    ):
        rows.append(
            {
                "symbol": "AMZN",
                "trade_date": date,
                "close": close,
                "signal": float(signal),
                "momentum": float(signal) / 10.0,
                "target_up_big_move_t3": 1.0 if idx == 5 else np.nan,
            }
        )

    for idx, (date, signal, close) in enumerate(zip(dates, tsla_signal, tsla_close, strict=False)):
        rows.append(
            {
                "symbol": "TSLA",
                "trade_date": date,
                "close": close,
                "signal": float(signal),
                "momentum": float(signal) / 10.0,
                "target_up_big_move_t3": 1.0 if idx == 5 else np.nan,
            }
        )

    frame = pd.DataFrame(rows)
    query = frame.loc[frame["symbol"] == "MSFT"].copy()

    summary = find_similar_historical_periods(
        frame,
        query,
        feature_columns=["signal", "momentum"],
        window_size=4,
        top_k=3,
        future_horizon_days=3,
    )

    assert summary["n_matches"] == 3
    assert summary["same_symbol_matches"] == 1
    assert summary["peer_group_matches"] == 1
    assert summary["market_matches"] == 1
    assert summary["cross_symbol_matches"] == 2
    assert summary["strategy"] == "same_symbol_then_peer_group_then_market"
    assert summary["matches"][0]["symbol"] == "MSFT"
    assert summary["matches"][0]["scope"] == "same_symbol"
    assert summary["matches"][1]["symbol"] == "AMZN"
    assert summary["matches"][1]["scope"] == "peer_group"
    assert summary["matches"][2]["symbol"] == "TSLA"
    assert summary["matches"][2]["scope"] == "market"


def test_build_markdown_report_includes_historical_similarity_block():
    markdown = build_markdown_report(
        ticker="AAPL",
        prob_up=0.67,
        metrics={
            "mean_accuracy": 0.58,
            "mean_auc": 0.61,
            "train_test_split": "PanelTimeSeriesSplit_n5",
        },
        shap_summary={
            "top_positive": [{"feature": "ret_1d_residual", "value": 0.12, "shap": 0.08}],
            "top_negative": [{"feature": "market_volatility_5d", "value": 0.3, "shap": -0.05}],
        },
        historical_similarity={
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
        target_label="an upside move greater than 2% within the next 3 trading days",
        model_label="LightGBM Panel",
    )

    assert "Historical Analog Windows" in markdown
    assert "average similarity" in markdown
    assert "MSFT" in markdown
    assert "subsequent 3-day return" in markdown
    assert "same symbol first, then peer group, then market fallback" in markdown
    assert "Final trading signal" in markdown
