"""Feature engineering: one row per trading day per ticker.

Combines news sentiment features with technical indicators.
All features use shift(1) or past windows to prevent look-ahead leakage.
"""

import logging
from typing import Sequence

import numpy as np
import pandas as pd

from app.database import get_conn

logger = logging.getLogger(__name__)

BIG_MOVE_THRESHOLD = 0.02
BIG_MOVE_HORIZON_DAYS = 3
TEXT_BLOB_COL = "news_text_blob"


def _load_news_features(symbol: str) -> pd.DataFrame:
    """Aggregate news_aligned + layer1_results per trade_date."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT na.trade_date,
               COUNT(*)                                          AS n_articles,
               SUM(CASE WHEN l1.relevance = 'relevant' THEN 1 ELSE 0 END) AS n_relevant,
               SUM(CASE WHEN l1.sentiment = 'positive' THEN 1 ELSE 0 END) AS n_positive,
               SUM(CASE WHEN l1.sentiment = 'negative' THEN 1 ELSE 0 END) AS n_negative,
               SUM(CASE WHEN l1.sentiment = 'neutral'  THEN 1 ELSE 0 END) AS n_neutral,
               GROUP_CONCAT(
                   TRIM(
                       COALESCE(n.title, '') || ' ' ||
                       COALESCE(n.description, '') || ' ' ||
                       COALESCE(l1.key_discussion, '') || ' ' ||
                       COALESCE(l1.reason_growth, '') || ' ' ||
                       COALESCE(l1.reason_decrease, '')
                   ),
                   ' '
               ) AS news_text_blob
        FROM news_aligned na
        JOIN news n ON na.news_id = n.id
        JOIN layer1_results l1 ON na.news_id = l1.news_id AND na.symbol = l1.symbol
        WHERE na.symbol = ?
        GROUP BY na.trade_date
        ORDER BY na.trade_date
        """,
        (symbol,),
    ).fetchall()
    conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    total = df["n_articles"].clip(lower=1)
    df["sentiment_score"] = (df["n_positive"] - df["n_negative"]) / total
    df["relevance_ratio"] = df["n_relevant"] / total
    df["positive_ratio"] = df["n_positive"] / total
    df["negative_ratio"] = df["n_negative"] / total
    df["has_news"] = 1
    df[TEXT_BLOB_COL] = df[TEXT_BLOB_COL].fillna("").astype(str)
    return df


def _load_ohlc(symbol: str) -> pd.DataFrame:
    """Load OHLC data for a symbol."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM ohlc WHERE symbol = ? ORDER BY date",
        (symbol,),
    ).fetchall()
    conn.close()
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_features(
    symbol: str,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    big_move_threshold: float = BIG_MOVE_THRESHOLD,
    big_move_horizon_days: int = BIG_MOVE_HORIZON_DAYS,
) -> pd.DataFrame:
    """Build feature matrix: one row per trading day.

    All features use shift(1) or past windows to prevent look-ahead leakage.
    Target: whether close > previous close (binary up/down).

    Args:
        symbol: Stock ticker symbol.

    Returns:
        DataFrame with features and targets, or empty DataFrame if insufficient data.
    """
    ohlc = _load_ohlc(symbol)
    if ohlc.empty or len(ohlc) < 30:
        logger.warning(f"Insufficient OHLC data for {symbol}")
        return pd.DataFrame()

    news = _load_news_features(symbol)

    # Merge news onto OHLC dates
    df = ohlc.rename(columns={"date": "trade_date"})
    if not news.empty:
        df = df.merge(news, on="trade_date", how="left")
    else:
        for col in [
            "n_articles",
            "n_relevant",
            "n_positive",
            "n_negative",
            "n_neutral",
            "sentiment_score",
            "relevance_ratio",
            "positive_ratio",
            "negative_ratio",
            "has_news",
        ]:
            df[col] = 0
        df[TEXT_BLOB_COL] = ""

    # Fill missing news days
    news_cols = [
        "n_articles",
        "n_relevant",
        "n_positive",
        "n_negative",
        "n_neutral",
        "sentiment_score",
        "relevance_ratio",
        "positive_ratio",
        "negative_ratio",
        "has_news",
    ]
    df[news_cols] = df[news_cols].fillna(0)
    df[TEXT_BLOB_COL] = df[TEXT_BLOB_COL].fillna("").astype(str)

    # --- Rolling news features (use current + past, no shift needed since news is pre-market/same day) ---
    for w in [3, 5, 10]:
        df[f"sentiment_score_{w}d"] = df["sentiment_score"].rolling(w, min_periods=1).mean()
        df[f"positive_ratio_{w}d"] = df["positive_ratio"].rolling(w, min_periods=1).mean()
        df[f"negative_ratio_{w}d"] = df["negative_ratio"].rolling(w, min_periods=1).mean()
        df[f"news_count_{w}d"] = df["n_articles"].rolling(w, min_periods=1).sum()

    # Sentiment momentum: 3d mean - 10d mean
    df["sentiment_momentum_3d"] = df["sentiment_score_3d"] - df["sentiment_score_10d"]

    # --- Price / technical features (shifted by 1 to prevent leakage) ---
    close = df["close"]
    df["ret_1d"] = close.pct_change(1).shift(1)
    df["ret_3d"] = close.pct_change(3).shift(1)
    df["ret_5d"] = close.pct_change(5).shift(1)
    df["ret_10d"] = close.pct_change(10).shift(1)

    df["volatility_5d"] = close.pct_change().rolling(5).std().shift(1)
    df["volatility_10d"] = close.pct_change().rolling(10).std().shift(1)

    avg_vol_5 = df["volume"].rolling(5).mean().shift(1)
    df["volume_ratio_5d"] = df["volume"].shift(1) / avg_vol_5.clip(lower=1)

    df["gap"] = (df["open"] / close.shift(1) - 1).shift(1)

    ma5 = close.rolling(5).mean().shift(1)
    ma20 = close.rolling(20).mean().shift(1)
    df["ma5_vs_ma20"] = ma5 / ma20.clip(lower=0.01) - 1

    # RSI 14
    delta = close.diff().shift(1)
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.clip(lower=1e-10)
    df["rsi_14"] = 100 - 100 / (1 + rs)

    df["day_of_week"] = df["trade_date"].dt.dayofweek

    # --- Targets: next-N-day direction ---
    df["target_t1"] = (close.shift(-1) > close).astype(int)
    df["target_t3"] = (close.shift(-3) > close).astype(int)
    df["target_t5"] = (close.shift(-5) > close).astype(int)

    # Noise-reduced event labels: future 3-day absolute/upside move > threshold.
    future_return = close.shift(-big_move_horizon_days) / close - 1.0
    has_future = future_return.notna()
    df["target_big_move_t3"] = np.where(
        has_future,
        (future_return.abs() > big_move_threshold).astype(int),
        np.nan,
    )
    df["target_up_big_move_t3"] = np.where(
        has_future,
        (future_return > big_move_threshold).astype(int),
        np.nan,
    )

    # Drop partial indicator warm-up rows so sequential models never see NaNs.
    df = df.dropna(subset=FEATURE_COLS).reset_index(drop=True)

    if start_date is not None:
        start_ts = pd.Timestamp(start_date)
        df = df.loc[df["trade_date"] >= start_ts]
    if end_date is not None:
        end_ts = pd.Timestamp(end_date)
        df = df.loc[df["trade_date"] <= end_ts]
    df = df.reset_index(drop=True)

    logger.info(f"Built {len(df)} feature rows for {symbol}")
    return df


# Feature columns for ML models
FEATURE_COLS = [
    # News
    "n_articles",
    "n_relevant",
    "n_positive",
    "n_negative",
    "n_neutral",
    "sentiment_score",
    "relevance_ratio",
    "positive_ratio",
    "negative_ratio",
    "has_news",
    # Rolling news
    "sentiment_score_3d",
    "sentiment_score_5d",
    "sentiment_score_10d",
    "positive_ratio_3d",
    "positive_ratio_5d",
    "positive_ratio_10d",
    "negative_ratio_3d",
    "negative_ratio_5d",
    "negative_ratio_10d",
    "news_count_3d",
    "news_count_5d",
    "news_count_10d",
    "sentiment_momentum_3d",
    # Price / tech
    "ret_1d",
    "ret_3d",
    "ret_5d",
    "ret_10d",
    "volatility_5d",
    "volatility_10d",
    "volume_ratio_5d",
    "gap",
    "ma5_vs_ma20",
    "rsi_14",
    "day_of_week",
]

PANEL_MARKET_FEATURE_COLS = [
    "market_sentiment_score",
    "market_positive_ratio",
    "market_negative_ratio",
    "market_news_count_3d",
    "market_ret_1d",
    "market_volatility_5d",
    "market_has_news_ratio",
    "sentiment_score_residual",
    "news_count_3d_residual",
    "ret_1d_residual",
]

TARGET_COLS = [
    "target_t1",
    "target_t3",
    "target_t5",
    "target_big_move_t3",
    "target_up_big_move_t3",
]

PANEL_CATEGORICAL_COLS = ["symbol"]
PANEL_FEATURE_COLS = PANEL_CATEGORICAL_COLS + FEATURE_COLS + PANEL_MARKET_FEATURE_COLS


def _add_market_relative_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add cross-sectional market context features to a panel frame."""

    out = panel.copy()
    grouped = out.groupby("trade_date", sort=False)

    market_mean_map = {
        "sentiment_score": "market_sentiment_score",
        "positive_ratio": "market_positive_ratio",
        "negative_ratio": "market_negative_ratio",
        "news_count_3d": "market_news_count_3d",
        "ret_1d": "market_ret_1d",
        "volatility_5d": "market_volatility_5d",
        "has_news": "market_has_news_ratio",
    }
    for source_col, target_col in market_mean_map.items():
        if source_col in out.columns:
            out[target_col] = grouped[source_col].transform("mean")

    residual_map = {
        "sentiment_score": ("market_sentiment_score", "sentiment_score_residual"),
        "news_count_3d": ("market_news_count_3d", "news_count_3d_residual"),
        "ret_1d": ("market_ret_1d", "ret_1d_residual"),
    }
    for source_col, (market_col, residual_col) in residual_map.items():
        if source_col in out.columns and market_col in out.columns:
            out[residual_col] = out[source_col] - out[market_col]

    return out


def list_panel_symbols() -> list[str]:
    """Return the default stock universe for panel training."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT symbol
        FROM tickers
        ORDER BY symbol
        """
    ).fetchall()
    conn.close()
    return [str(row["symbol"]).strip().upper() for row in rows if row["symbol"]]


def build_panel_features(
    symbols: Sequence[str] | None = None,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    big_move_threshold: float = BIG_MOVE_THRESHOLD,
    big_move_horizon_days: int = BIG_MOVE_HORIZON_DAYS,
) -> pd.DataFrame:
    """Build a unified panel dataset across multiple symbols.

    The returned frame is sorted by ``trade_date`` then ``symbol`` and includes
    a categorical ``symbol`` column suitable for LightGBM panel training.
    """

    symbol_list = [s.strip().upper() for s in (symbols or list_panel_symbols()) if s and s.strip()]
    frames: list[pd.DataFrame] = []

    for symbol in symbol_list:
        df = build_features(
            symbol,
            start_date=start_date,
            end_date=end_date,
            big_move_threshold=big_move_threshold,
            big_move_horizon_days=big_move_horizon_days,
        )
        if df.empty:
            logger.warning("Skipping %s in panel build because feature set is empty.", symbol)
            continue

        df = df.copy()
        df.insert(0, "symbol", symbol)
        frames.append(df)

    if not frames:
        return pd.DataFrame(
            columns=[
                "symbol",
                "trade_date",
                TEXT_BLOB_COL,
                *FEATURE_COLS,
                *PANEL_MARKET_FEATURE_COLS,
                *TARGET_COLS,
            ]
        )

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    panel = _add_market_relative_features(panel)
    panel["symbol"] = panel["symbol"].astype("category")

    logger.info(
        "Built panel feature matrix with %s rows across %s symbols.",
        len(panel),
        panel["symbol"].nunique(),
    )
    return panel
