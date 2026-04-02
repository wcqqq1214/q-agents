from __future__ import annotations

import numpy as np
import pandas as pd

import app.ml.features as ml_features
from app.ml.model_trainer import predict_proba_latest, train_lightgbm_panel


def _make_mock_ohlc(periods: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=periods)
    close = 100.0 * np.power(1.01, np.arange(periods))
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.995,
            "high": close * 1.005,
            "low": close * 0.99,
            "close": close,
            "volume": np.linspace(1_000_000, 1_500_000, periods),
        }
    )


def test_build_features_adds_big_move_targets(monkeypatch):
    monkeypatch.setattr(ml_features, "_load_ohlc", lambda symbol: _make_mock_ohlc())
    monkeypatch.setattr(ml_features, "_load_news_features", lambda symbol: pd.DataFrame())

    df = ml_features.build_features("AAPL")

    assert "target_big_move_t3" in df.columns
    assert "target_up_big_move_t3" in df.columns
    assert df["target_big_move_t3"].dropna().eq(1).all()
    assert df["target_up_big_move_t3"].dropna().eq(1).all()
    assert df["target_big_move_t3"].tail(3).isna().all()
    assert df["target_up_big_move_t3"].tail(3).isna().all()


def test_build_features_respects_date_range(monkeypatch):
    monkeypatch.setattr(ml_features, "_load_ohlc", lambda symbol: _make_mock_ohlc())
    monkeypatch.setattr(ml_features, "_load_news_features", lambda symbol: pd.DataFrame())

    df = ml_features.build_features(
        "AAPL",
        start_date="2024-01-22",
        end_date="2024-02-09",
    )

    assert not df.empty
    assert df["trade_date"].min() >= pd.Timestamp("2024-01-22")
    assert df["trade_date"].max() <= pd.Timestamp("2024-02-09")


def test_build_features_drops_partial_indicator_rows(monkeypatch):
    monkeypatch.setattr(ml_features, "_load_ohlc", lambda symbol: _make_mock_ohlc(periods=60))
    monkeypatch.setattr(ml_features, "_load_news_features", lambda symbol: pd.DataFrame())

    df = ml_features.build_features("AAPL")

    assert not df.empty
    assert not df[ml_features.FEATURE_COLS].isna().any().any()


def test_build_panel_features_concatenates_and_sorts(monkeypatch):
    data_map = {
        "MSFT": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-03", "2024-01-04"]),
                "ret_1d": [0.1, 0.2],
                "target_t1": [0, 1],
            }
        ),
        "AAPL": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-04"]),
                "ret_1d": [0.3, 0.4],
                "target_t1": [1, 0],
            }
        ),
    }

    monkeypatch.setattr(ml_features, "list_panel_symbols", lambda: ["MSFT", "AAPL"])
    monkeypatch.setattr(
        ml_features,
        "build_features",
        lambda symbol, **kwargs: data_map[symbol].copy(),
    )

    panel = ml_features.build_panel_features()

    assert panel["symbol"].dtype.name == "category"
    assert panel["symbol"].astype(str).tolist() == ["AAPL", "MSFT", "AAPL", "MSFT"]
    assert panel["trade_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-04",
    ]


def test_build_panel_features_adds_market_relative_features(monkeypatch):
    data_map = {
        "AAPL": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "sentiment_score": [0.6, 0.2],
                "positive_ratio": [0.8, 0.4],
                "negative_ratio": [0.1, 0.3],
                "news_count_3d": [10, 8],
                "ret_1d": [0.03, 0.01],
                "volatility_5d": [0.2, 0.25],
                "has_news": [1, 1],
                "target_t1": [1, 0],
            }
        ),
        "MSFT": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "sentiment_score": [0.2, -0.1],
                "positive_ratio": [0.5, 0.2],
                "negative_ratio": [0.2, 0.5],
                "news_count_3d": [6, 4],
                "ret_1d": [0.01, -0.02],
                "volatility_5d": [0.1, 0.2],
                "has_news": [1, 0],
                "target_t1": [0, 1],
            }
        ),
    }

    monkeypatch.setattr(ml_features, "list_panel_symbols", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(
        ml_features,
        "build_features",
        lambda symbol, **kwargs: data_map[symbol].copy(),
    )

    panel = ml_features.build_panel_features()

    first_day = panel.loc[panel["trade_date"] == pd.Timestamp("2024-01-02")].reset_index(drop=True)
    assert np.isclose(first_day.loc[0, "market_sentiment_score"], 0.4)
    assert np.isclose(first_day.loc[1, "market_sentiment_score"], 0.4)
    assert np.isclose(first_day.loc[0, "sentiment_score_residual"], 0.2)
    assert np.isclose(first_day.loc[1, "sentiment_score_residual"], -0.2)
    assert np.isclose(first_day.loc[0, "market_ret_1d"], 0.02)
    assert np.isclose(first_day.loc[1, "ret_1d_residual"], -0.01)
    assert np.isclose(first_day.loc[0, "market_has_news_ratio"], 1.0)


def test_train_lightgbm_panel_with_categorical_symbol():
    trade_dates = []
    labels = []
    rows = []

    for i, trade_date in enumerate(pd.bdate_range("2024-01-01", periods=120)):
        label = 1 if i % 6 < 3 else 0
        for symbol, offset in [("AAPL", -0.25), ("MSFT", 0.25)]:
            rows.append(
                {
                    "symbol": symbol,
                    "signal": float(i % 6) + offset,
                    "momentum": float((i % 10) - 5),
                }
            )
            labels.append(label)
            trade_dates.append(trade_date)

    X = pd.DataFrame(rows)
    X["symbol"] = X["symbol"].astype("category")
    y = pd.Series(labels)
    dates = pd.Series(trade_dates)

    model, metrics = train_lightgbm_panel(
        X,
        y,
        dates,
        categorical_features=["symbol"],
        n_splits=3,
    )

    assert metrics["train_test_split"] == "PanelTimeSeriesSplit_n3"
    assert metrics["cv_unit"] == "trade_date"
    assert metrics["n_unique_dates"] == 120

    proba = predict_proba_latest(model, X.tail(1))
    assert isinstance(proba, float)
    assert 0.0 <= proba <= 1.0
