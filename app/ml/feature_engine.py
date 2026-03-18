from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf


@dataclass
class FeatureConfig:
    """Configuration for the feature engineering pipeline.

    This configuration is intentionally lightweight for now but provides a
    single place to adjust lookback windows in a controlled way if needed
    later. All defaults are chosen to match the conventions described in
    ``ml_quant.md``.

    Attributes:
        r1_window: Lookback window (in trading days) for the 1-day return
            feature. This is effectively ``pct_change(1)`` but is kept as a
            parameter for completeness.
        r3_window: Lookback window for the 3-day simple return feature.
        r5_window: Lookback window for the 5-day simple return feature.
        rsi_window: Lookback window for the RSI indicator.
        cci_window: Lookback window for the CCI indicator.
        sma_short: Window for the short simple moving average used in the
            trend-distance features (e.g. 20 days).
        sma_long: Window for the longer SMA used in the trend-distance
            features (e.g. 50 days).
        atr_window: Lookback window for the ATR volatility indicator.
        bb_window: Lookback window for the Bollinger Bands midline.
        bb_std: Standard deviation multiplier for Bollinger Bands.
        volume_ma_window: Window for the moving-average volume used in the
            ``Volume_Ratio`` feature.
        label_threshold: Threshold epsilon for the 3-day smoothed direction
            label; samples with |R_future| <= epsilon are dropped (oscillation).
            Default 0.005 (0.5%).
    """

    r1_window: int = 1
    r3_window: int = 3
    r5_window: int = 5
    rsi_window: int = 14
    cci_window: int = 14
    sma_short: int = 20
    sma_long: int = 50
    atr_window: int = 14
    bb_window: int = 5
    bb_std: float = 2.0
    volume_ma_window: int = 5
    label_threshold: float = 0.005


def load_ohlcv(ticker: str, period_years: int = 5) -> pd.DataFrame:
    """Load daily OHLCV history for a ticker using yfinance.

    This helper function provides the raw price and volume history required
    by the downstream feature engineering pipeline. It is intentionally
    conservative and focuses on a simple daily frequency as described in
    ``ml_quant.md``.

    The function:

    - normalizes and uppercases the ticker symbol;
    - requests a configurable number of years of history at daily resolution
      using ``yfinance.download`` (5 years by default);
    - sorts by date in ascending order; and
    - drops any rows containing missing values in the OHLCV columns.

    Args:
        ticker: Asset symbol accepted by Yahoo Finance (e.g. ``\"AAPL\"``,
            ``\"NVDA\"``, ``\"BTC-USD\"``, ``\"DOGE-USD\"``).
        period_years: Minimum number of calendar years of history to request.
            The value is converted to a yfinance ``period`` string such as
            ``\"3y\"``.

    Returns:
        A pandas DataFrame indexed by date with at least the following
        columns: ``Open``, ``High``, ``Low``, ``Close``, ``Volume``. Rows
        with missing values in any of these columns are dropped.

    Raises:
        ValueError: If ``ticker`` is empty or if no valid OHLCV data can be
            retrieved from yfinance.
    """

    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is empty.")

    period_str = f"{max(int(period_years), 1)}y"
    # Disable yfinance's progress bar to avoid noisy console output.
    df = yf.download(
        normalized,
        period=period_str,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise ValueError(f"yfinance returned no data for ticker={normalized!r}.")

    # yfinance can return either a flat Index or a MultiIndex for columns.
    # For a single ticker with a MultiIndex, we select the slice associated
    # with the requested symbol.
    if isinstance(df.columns, pd.MultiIndex):
        if normalized in df.columns.get_level_values(0):
            df = df.xs(normalized, axis=1, level=0)
        elif normalized in df.columns.get_level_values(1):
            df = df.xs(normalized, axis=1, level=1)
        else:
            # Fall back to the first level if we cannot match the ticker name.
            df = df.droplevel(0, axis=1)

    # Standardize column names in a case-insensitive way and ensure the
    # expected OHLCV set is present.
    rename_map: dict[str, str] = {}
    for col in df.columns:
        key = str(col).lower()
        if key == "open":
            rename_map[col] = "Open"
        elif key == "high":
            rename_map[col] = "High"
        elif key == "low":
            rename_map[col] = "Low"
        elif key == "close":
            rename_map[col] = "Close"
        elif key in {"adj close", "adjclose", "adjusted close"}:
            rename_map[col] = "Adj Close"
        elif key == "volume":
            rename_map[col] = "Volume"

    if rename_map:
        df = df.rename(columns=rename_map)

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Downloaded data for {normalized!r} is missing columns: {missing}."
        )

    df = df.sort_index()
    df = df.dropna(subset=required_cols)
    return df


def _download_single_ohlcv(symbol: str, period_str: str) -> pd.DataFrame:
    """Download OHLCV for a single symbol; return DataFrame with standard column names."""
    try:
        raw = yf.download(
            symbol,
            period=period_str,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
    except Exception:
        return pd.DataFrame()
    if raw.empty:
        return raw
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in raw.columns.get_level_values(0):
            raw = raw.xs(symbol, axis=1, level=0)
        elif symbol in raw.columns.get_level_values(1):
            raw = raw.xs(symbol, axis=1, level=1)
        else:
            raw = raw.droplevel(0, axis=1)
    rename_map: dict[str, str] = {}
    for col in raw.columns:
        key = str(col).lower()
        if key == "open":
            rename_map[col] = "Open"
        elif key == "high":
            rename_map[col] = "High"
        elif key == "low":
            rename_map[col] = "Low"
        elif key == "close":
            rename_map[col] = "Close"
        elif key in {"adj close", "adjclose", "adjusted close"}:
            rename_map[col] = "Adj Close"
        elif key == "volume":
            rename_map[col] = "Volume"
    if rename_map:
        raw = raw.rename(columns=rename_map)
    return raw.sort_index()


def load_ohlcv_with_macro(ticker: str, period_years: int = 5) -> pd.DataFrame:
    """Load main ticker OHLCV plus DXY and VIX, aligned by date (inner join).

    Fetches the primary asset (e.g. BTC-USD), dollar index (DX-Y.NYB) and VIX (^VIX),
    then merges them on the date index. DXY contributes 1d and 5d returns; VIX
    contributes raw Close as a volatility environment feature. Rows missing any
    of these after merge are dropped so downstream feature/label code sees a
    consistent panel.

    Args:
        ticker: Main asset symbol (e.g. \"BTC-USD\", \"AAPL\").
        period_years: Years of history to request (converted to yfinance period).

    Returns:
        DataFrame indexed by date (ascending) with columns: Open, High, Low,
        Close, Volume (main), and DXY_Ret_1d, DXY_Ret_5d, VIX.
    """
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is empty.")
    period_str = f"{max(int(period_years), 1)}y"

    main = load_ohlcv(normalized, period_years=period_years)
    required = ["Open", "High", "Low", "Close", "Volume"]
    for c in required:
        if c not in main.columns:
            raise ValueError(f"Main ticker missing column: {c}.")

    # DXY: DX-Y.NYB, keep Close and compute returns (only add if fetch succeeded)
    dxy = _download_single_ohlcv("DX-Y.NYB", period_str)
    has_dxy = not (dxy.empty or "Close" not in dxy.columns)
    macro_cols: list[str] = []

    out = main.copy()
    if has_dxy:
        dxy_close = dxy["Close"].reindex(main.index)
        out["DXY_Ret_1d"] = dxy_close.pct_change(1)
        out["DXY_Ret_5d"] = dxy_close.pct_change(5)
        macro_cols.extend(["DXY_Ret_1d", "DXY_Ret_5d"])

    # VIX: ^VIX, keep Close (only add if fetch succeeded)
    vix_raw = _download_single_ohlcv("^VIX", period_str)
    has_vix = not (vix_raw.empty or "Close" not in vix_raw.columns)
    if has_vix:
        out["VIX"] = vix_raw["Close"].reindex(main.index)
        macro_cols.append("VIX")

    if macro_cols:
        out = out.dropna(subset=macro_cols)
    return out


def calculate_rolling_zscore(
    df: pd.DataFrame,
    column: str,
    window: int = 60,
) -> pd.Series:
    """Compute a rolling z-score for a given column over a fixed window.

    For each time step t this uses the previous ``window`` observations of the
    series to compute a mean and standard deviation and then returns::

        Z_t = (X_t - mean_window) / std_window

    If there are fewer than ``window`` observations available or the rolling
    standard deviation is zero, the result is ``NaN`` at that position.
    """

    series = df[column].astype(float)
    rolling = series.rolling(window=window, min_periods=window)
    mu = rolling.mean()
    sigma = rolling.std(ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (series - mu) / sigma
    # Avoid inf values where sigma is zero.
    z = z.where(sigma > 0)
    return z


def _compute_returns_features(df: pd.DataFrame, cfg: FeatureConfig) -> pd.DataFrame:
    """Compute simple return-based features from OHLCV history."""

    out = df.copy()
    close = out["Close"]
    out["Ret_1d"] = close.pct_change(cfg.r1_window)
    out["Ret_3d"] = close.pct_change(cfg.r3_window)
    out["Ret_5d"] = close.pct_change(cfg.r5_window)
    return out


def _compute_momentum_features(df: pd.DataFrame, cfg: FeatureConfig) -> pd.DataFrame:
    """Compute momentum and oscillator style features using pandas_ta."""

    out = df.copy()
    close = out["Close"]

    # RSI
    rsi_series = ta.rsi(close, length=cfg.rsi_window)
    out["RSI_14"] = rsi_series

    # MACD and histogram
    macd_df = ta.macd(close)
    if not macd_df.empty:
        # The default MACD column names follow the pattern MACD_{fast}_{slow}_{signal}
        macd_col = next((c for c in macd_df.columns if "MACD_" in c and "_signal" not in c and "_histogram" not in c), None)
        signal_col = next((c for c in macd_df.columns if "MACDs_" in c or "MACD_signal" in c), None)
        hist_col = next((c for c in macd_df.columns if "MACDh_" in c or "MACD_histogram" in c), None)

        if macd_col is None:
            macd_col = macd_df.columns[0]
        out["MACD"] = macd_df[macd_col]

        if signal_col is not None:
            out["MACD_Signal"] = macd_df[signal_col]
        else:
            out["MACD_Signal"] = out["MACD"].ewm(span=9, adjust=False).mean()

        if hist_col is not None:
            out["MACD_Hist"] = macd_df[hist_col]
        else:
            out["MACD_Hist"] = out["MACD"] - out["MACD_Signal"]

    # CCI
    cci = ta.cci(
        high=out["High"],
        low=out["Low"],
        close=out["Close"],
        length=cfg.cci_window,
    )
    out["CCI_14"] = cci

    # ADX and directional indicators (trend strength).
    adx_df = ta.adx(
        high=out["High"],
        low=out["Low"],
        close=out["Close"],
        length=14,
    )
    if adx_df is not None and not adx_df.empty:
        adx_col = next((c for c in adx_df.columns if "ADX_" in c), None)
        plus_col = next((c for c in adx_df.columns if "DMP_" in c or "+DI" in c), None)
        minus_col = next((c for c in adx_df.columns if "DMN_" in c or "-DI" in c), None)
        if adx_col is None:
            adx_col = adx_df.columns[0]
        out["ADX_14"] = adx_df[adx_col]
        if plus_col is not None:
            out["PlusDI_14"] = adx_df[plus_col]
        if minus_col is not None:
            out["MinusDI_14"] = adx_df[minus_col]

    # Aroon indicator (trend start/exhaustion).
    aroon_df = ta.aroon(
        high=out["High"],
        low=out["Low"],
        length=14,
    )
    if aroon_df is not None and not aroon_df.empty:
        up_col = next((c for c in aroon_df.columns if "AROONU" in c or "UP_" in c), None)
        down_col = next((c for c in aroon_df.columns if "AROOND" in c or "DN_" in c), None)
        if up_col is None:
            up_col = aroon_df.columns[0]
        if down_col is None and len(aroon_df.columns) > 1:
            down_col = aroon_df.columns[1]
        out["Aroon_Up_14"] = aroon_df[up_col]
        if down_col is not None:
            out["Aroon_Down_14"] = aroon_df[down_col]
    return out


def _compute_trend_distance_features(df: pd.DataFrame, cfg: FeatureConfig) -> pd.DataFrame:
    """Compute distance-to-trend features based on simple moving averages."""

    out = df.copy()
    close = out["Close"]
    sma_short = close.rolling(window=cfg.sma_short, min_periods=cfg.sma_short).mean()
    sma_long = close.rolling(window=cfg.sma_long, min_periods=cfg.sma_long).mean()

    out["SMA_20"] = sma_short
    out["SMA_50"] = sma_long
    out["Dist_SMA_20"] = close / sma_short - 1.0
    out["Dist_SMA_50"] = close / sma_long - 1.0
    return out


def _compute_volatility_volume_features(
    df: pd.DataFrame,
    cfg: FeatureConfig,
) -> pd.DataFrame:
    """Compute volatility and volume-related features."""

    out = df.copy()

    # ATR for volatility.
    atr = ta.atr(
        high=out["High"],
        low=out["Low"],
        close=out["Close"],
        length=cfg.atr_window,
    )
    out["ATR_14"] = atr

    # Bollinger Bands.
    bb = ta.bbands(
        close=out["Close"],
        length=cfg.bb_window,
        std=cfg.bb_std,
    )
    if not bb.empty:
        lower_col = next((c for c in bb.columns if "BBL" in c), bb.columns[0])
        upper_col = next((c for c in bb.columns if "BBU" in c), bb.columns[-1])
        out["BBL_5_2.0"] = bb[lower_col]
        out["BBU_5_2.0"] = bb[upper_col]

    # Volume ratio versus a short moving average.
    volume = out["Volume"].astype(float)
    vol_ma = volume.rolling(
        window=cfg.volume_ma_window,
        min_periods=cfg.volume_ma_window,
    ).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["Volume_Ratio"] = volume / vol_ma
    return out


def build_dataset(
    df: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Transform raw OHLCV (optionally with macro columns) into a supervised dataset.

    v3 label (ml_quant_optimization_v3.md): predict next-day intraday return
    (open-to-close) with a dynamic ATR-based threshold to avoid overnight gaps.

    - Derive technical features (returns, momentum, trend-distance, volatility/volume).
    - If present, keep macro columns (DXY_Ret_1d, DXY_Ret_5d, VIX) from ``df``.
    - Next-day intraday return: R_intraday,t+1 = (Close_{t+1} - Open_{t+1}) / Open_{t+1},
      aligned to row t via shift(-1). Dynamic threshold (v4): eps_t = 0.25 * ATR_14,t / Close_t.
    - Label: Y_t = 1 if R_intraday > eps_t, 0 if R_intraday < -eps_t, else NaN.
      Rows with NaN label (last row or |R_intraday| <= eps_t) are dropped.
    - ``label_threshold`` in cfg is unused in v3 (dynamic threshold only).

    Args:
        df: DataFrame with at least ``Open``, ``High``, ``Low``, ``Close``,
            ``Volume``; may include ``DXY_Ret_1d``, ``DXY_Ret_5d``, ``VIX``.
        cfg: Optional feature config (label_threshold not used for v3 label).

    Returns:
        ``(X, y)``: feature matrix and binary label series, index-aligned.

    Raises:
        ValueError: If fewer than 100 rows remain after label/feature filtering.
    """

    if cfg is None:
        cfg = FeatureConfig()

    if df.empty:
        raise ValueError("Input OHLCV DataFrame is empty.")

    # Build up the feature set step by step (uses main OHLCV only for tech indicators).
    features = df.copy()
    features = _compute_returns_features(features, cfg)
    features = _compute_momentum_features(features, cfg)
    features = _compute_trend_distance_features(features, cfg)
    features = _compute_volatility_volume_features(features, cfg)
    # Apply rolling Z-Score normalisation to oscillators and distance features.
    zscore_cols = [
        "RSI_14",
        "CCI_14",
        "MACD_Hist",
        "Volume_Ratio",
        "Dist_SMA_20",
        "Dist_SMA_50",
    ]
    for col in zscore_cols:
        if col in features.columns:
            features[col] = calculate_rolling_zscore(features, col, window=60)

    # v3: next-day intraday return (open-to-close) and dynamic ATR-based threshold.
    open_next = features["Open"].shift(-1)
    close_next = features["Close"].shift(-1)
    r_intraday = (close_next - open_next) / open_next
    eps_t = 0.25 * (features["ATR_14"] / features["Close"])
    label = np.where(
        r_intraday > eps_t,
        1,
        np.where(r_intraday < -eps_t, 0, np.nan),
    )

    # Combine features and label; drop rows with NaN label (no next day or oscillation).
    data = features.assign(label=label)
    data = data.dropna(subset=["label"])
    data = data.dropna()

    if data.shape[0] < 100:
        raise ValueError(
            "After feature engineering and NaN filtering, fewer than 100 rows "
            "remain. This is insufficient for a meaningful time-series split."
        )

    # Remove any absolute price columns from the feature matrix to stay close
    # to the design philosophy of using relative/indicator features. We keep
    # volume only through ``Volume_Ratio``.
    drop_cols = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in data.columns]
    data = data.drop(columns=drop_cols)

    y = data["label"].astype(int)
    X = data.drop(columns=["label"])
    return X, y

