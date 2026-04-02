from __future__ import annotations

import math
import time
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from app.ml.text_features import (
    DEFAULT_TEXT_SVD_COMPONENTS,
    TextSVDArtifacts,
    fit_text_svd_features,
)

# Strong regularization for low signal-to-noise financial data (new_ml_quant.md).
LGBM_PARAMS: Dict[str, object] = {
    "objective": "binary",
    "metric": "auc",
    "n_estimators": 200,
    "learning_rate": 0.01,
    "max_depth": 3,
    "num_leaves": 7,
    "min_child_samples": 50,
    "subsample": 0.6,
    "colsample_bytree": 0.5,
    "reg_alpha": 1.0,
    "reg_lambda": 1.0,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
    "verbosity": -1,
}


def _fit_lightgbm_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    categorical_features: Sequence[str] | None = None,
) -> LGBMClassifier:
    """Fit a LightGBM classifier with optional categorical features."""

    clf = LGBMClassifier(**LGBM_PARAMS)
    fit_kwargs: Dict[str, object] = {}
    if categorical_features:
        fit_kwargs["categorical_feature"] = list(categorical_features)
    clf.fit(X, y, **fit_kwargs)
    return clf


def _combine_feature_frames(X: pd.DataFrame, text_features: pd.DataFrame) -> pd.DataFrame:
    """Append text features to a base feature matrix while preserving order."""

    base = X.reset_index(drop=True)
    text = text_features.reset_index(drop=True)
    return pd.concat([base, text], axis=1)


def _safe_binary_auc(y_true: pd.Series | np.ndarray, proba: Sequence[float] | np.ndarray) -> float:
    """Return ROC AUC when both classes exist; otherwise return NaN."""

    y_series = pd.Series(y_true).reset_index(drop=True)
    if y_series.nunique(dropna=False) < 2:
        return float("nan")

    try:
        return float(roc_auc_score(y_series, np.asarray(proba)))
    except Exception:
        return float("nan")


def _build_panel_oof_frame(
    X_test: pd.DataFrame,
    y_test: pd.Series,
    trade_dates: pd.Series,
    y_pred: Sequence[int] | np.ndarray,
    proba: Sequence[float] | np.ndarray,
) -> pd.DataFrame:
    """Build an out-of-fold evaluation frame for panel metrics."""

    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(pd.Series(trade_dates)).reset_index(drop=True),
            "y_true": pd.Series(y_test).reset_index(drop=True).astype(int),
            "y_pred": pd.Series(y_pred).reset_index(drop=True).astype(int),
            "y_proba": pd.Series(proba).reset_index(drop=True).astype(float),
        }
    )
    if "symbol" in X_test.columns:
        frame["symbol"] = X_test["symbol"].astype(str).reset_index(drop=True)
    return frame


def _summarize_panel_symbol_metrics(
    oof_frame: pd.DataFrame,
) -> tuple[Dict[str, float], Dict[str, float], Dict[str, int], List[str]]:
    """Aggregate per-symbol OOS metrics from concatenated panel test folds."""

    if oof_frame.empty or "symbol" not in oof_frame.columns:
        return {}, {}, {}, []

    per_ticker_auc: Dict[str, float] = {}
    per_ticker_accuracy: Dict[str, float] = {}
    per_ticker_eval_rows: Dict[str, int] = {}
    per_ticker_auc_unavailable: List[str] = []

    grouped = oof_frame.groupby("symbol", sort=True, observed=False)
    for symbol, group in grouped:
        symbol_key = str(symbol)
        per_ticker_eval_rows[symbol_key] = int(len(group))
        per_ticker_accuracy[symbol_key] = float(accuracy_score(group["y_true"], group["y_pred"]))

        auc = _safe_binary_auc(group["y_true"], group["y_proba"])
        if math.isfinite(auc):
            per_ticker_auc[symbol_key] = auc
        else:
            per_ticker_auc_unavailable.append(symbol_key)

    return per_ticker_auc, per_ticker_accuracy, per_ticker_eval_rows, per_ticker_auc_unavailable


def train_lightgbm(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
) -> Tuple[LGBMClassifier, Dict[str, float | str | List[float]]]:
    """Train LightGBM with time-series cross-validation and return a refit model.

    Uses ``TimeSeriesSplit(n_splits)`` so each fold trains on past data and
    evaluates on future data. Aggregates out-of-sample AUC and accuracy across
    folds, then refits a final model on the full dataset for downstream SHAP
    and inference.

    Args:
        X: Feature matrix, rows ordered in time (oldest first).
        y: Binary target aligned with ``X``.
        n_splits: Number of time-series splits (default 5).

    Returns:
        (model, metrics) where model is the full-sample refit LGBMClassifier
        and metrics includes mean_auc, mean_accuracy, fold_aucs,
        fold_accuracies, train_test_split, and backward-compatible
        accuracy/auc keys.
    """

    if X.empty:
        raise ValueError("Feature matrix X is empty.")
    if y.empty:
        raise ValueError("Target vector y is empty.")
    if len(X) != len(y):
        raise ValueError("X and y must have the same number of rows.")

    tss = TimeSeriesSplit(n_splits=n_splits)
    fold_aucs: List[float] = []
    fold_accuracies: List[float] = []
    start_time = time.time()
    for train_idx, test_idx in tss.split(X):
        X_train = X.iloc[train_idx]
        y_train = y.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_test = y.iloc[test_idx]

        model = _fit_lightgbm_classifier(X_train, y_train)

        y_pred = model.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))
        fold_accuracies.append(acc)

        try:
            proba = model.predict_proba(X_test)[:, 1]
            auc = float(roc_auc_score(y_test, proba))
        except Exception:
            auc = float("nan")
        fold_aucs.append(auc)
    if not fold_accuracies:
        raise ValueError("TimeSeriesSplit produced no folds.")

    model = _fit_lightgbm_classifier(X, y)
    training_time_seconds = time.time() - start_time

    mean_auc = float(np.nanmean(fold_aucs))
    mean_accuracy = float(np.mean(fold_accuracies))

    metrics: Dict[str, float | str | List[float]] = {
        "mean_auc": mean_auc,
        "mean_accuracy": mean_accuracy,
        "fold_aucs": fold_aucs,
        "fold_accuracies": fold_accuracies,
        "train_test_split": f"TimeSeriesSplit_n{n_splits}",
        "accuracy": mean_accuracy,
        "auc": mean_auc,
        "training_time_seconds": training_time_seconds,
    }
    return model, metrics


def train_lightgbm_panel(
    X: pd.DataFrame,
    y: pd.Series,
    trade_dates: pd.Series,
    *,
    categorical_features: Sequence[str] | None = None,
    n_splits: int = 5,
) -> Tuple[LGBMClassifier, Dict[str, float | str | List[float] | int]]:
    """Train a unified LightGBM model with panel-aware date blocking.

    Unlike row-wise ``TimeSeriesSplit``, this splitter operates on unique
    ``trade_date`` values so that every symbol on the same day lands in the
    same fold. This avoids leaking same-day panel information across train and
    test sets.
    """

    if X.empty:
        raise ValueError("Feature matrix X is empty.")
    if y.empty:
        raise ValueError("Target vector y is empty.")
    if trade_dates.empty:
        raise ValueError("trade_dates is empty.")
    if len(X) != len(y) or len(X) != len(trade_dates):
        raise ValueError("X, y, and trade_dates must have the same number of rows.")

    date_series = pd.to_datetime(pd.Series(trade_dates)).reset_index(drop=True)
    order = date_series.sort_values(kind="mergesort").index
    X_sorted = X.iloc[order].reset_index(drop=True)
    y_sorted = y.iloc[order].reset_index(drop=True)
    date_series = date_series.iloc[order].reset_index(drop=True)

    unique_dates = pd.Series(date_series.drop_duplicates().tolist())
    if len(unique_dates) <= n_splits:
        raise ValueError(
            f"Need more than {n_splits} unique trade dates for panel CV; got {len(unique_dates)}."
        )

    tss = TimeSeriesSplit(n_splits=n_splits)
    fold_aucs: List[float] = []
    fold_accuracies: List[float] = []
    oof_frames: List[pd.DataFrame] = []

    start_time = time.time()
    for train_idx, test_idx in tss.split(unique_dates):
        train_dates = unique_dates.iloc[train_idx]
        test_dates = unique_dates.iloc[test_idx]

        train_mask = date_series.isin(train_dates)
        test_mask = date_series.isin(test_dates)
        X_train = X_sorted.loc[train_mask]
        y_train = y_sorted.loc[train_mask]
        X_test = X_sorted.loc[test_mask]
        y_test = y_sorted.loc[test_mask]

        model = _fit_lightgbm_classifier(X_train, y_train, categorical_features)

        y_pred = model.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))
        fold_accuracies.append(acc)

        try:
            proba = model.predict_proba(X_test)[:, 1]
        except Exception:
            proba = np.full(len(X_test), np.nan)

        auc = _safe_binary_auc(y_test, proba)
        fold_aucs.append(auc)
        oof_frames.append(
            _build_panel_oof_frame(
                X_test,
                y_test,
                date_series.loc[test_mask],
                y_pred,
                proba,
            )
        )

    if not fold_accuracies:
        raise ValueError("Panel TimeSeriesSplit produced no folds.")

    model = _fit_lightgbm_classifier(X_sorted, y_sorted, categorical_features)
    training_time_seconds = time.time() - start_time

    mean_auc = float(np.nanmean(fold_aucs))
    mean_accuracy = float(np.mean(fold_accuracies))
    oof_frame = pd.concat(oof_frames, ignore_index=True) if oof_frames else pd.DataFrame()
    per_ticker_auc, per_ticker_accuracy, per_ticker_eval_rows, per_ticker_auc_unavailable = (
        _summarize_panel_symbol_metrics(oof_frame)
    )

    metrics: Dict[str, float | str | List[float] | int] = {
        "mean_auc": mean_auc,
        "mean_accuracy": mean_accuracy,
        "fold_aucs": fold_aucs,
        "fold_accuracies": fold_accuracies,
        "train_test_split": f"PanelTimeSeriesSplit_n{n_splits}",
        "cv_unit": "trade_date",
        "n_rows": int(len(X_sorted)),
        "n_unique_dates": int(len(unique_dates)),
        "accuracy": mean_accuracy,
        "auc": mean_auc,
        "training_time_seconds": training_time_seconds,
    }
    if per_ticker_eval_rows:
        metrics["per_ticker_auc"] = per_ticker_auc
        metrics["per_ticker_accuracy"] = per_ticker_accuracy
        metrics["per_ticker_eval_rows"] = per_ticker_eval_rows
        if per_ticker_auc_unavailable:
            metrics["per_ticker_auc_unavailable"] = per_ticker_auc_unavailable
    return model, metrics


def train_lightgbm_panel_with_text(
    X: pd.DataFrame,
    y: pd.Series,
    trade_dates: pd.Series,
    text_series: pd.Series,
    *,
    categorical_features: Sequence[str] | None = None,
    n_splits: int = 5,
    text_n_components: int = DEFAULT_TEXT_SVD_COMPONENTS,
) -> Tuple[
    LGBMClassifier,
    Dict[str, float | str | List[float] | int],
    TextSVDArtifacts | None,
    pd.DataFrame,
]:
    """Train a panel LightGBM with fold-isolated TF-IDF + SVD text features."""

    if len(X) != len(text_series):
        raise ValueError("X and text_series must have the same number of rows.")

    if X.empty:
        raise ValueError("Feature matrix X is empty.")
    if y.empty:
        raise ValueError("Target vector y is empty.")
    if trade_dates.empty:
        raise ValueError("trade_dates is empty.")
    if len(X) != len(y) or len(X) != len(trade_dates):
        raise ValueError("X, y, trade_dates, and text_series must have the same number of rows.")

    date_series = pd.to_datetime(pd.Series(trade_dates)).reset_index(drop=True)
    text_sorted = pd.Series(text_series).reset_index(drop=True)
    order = date_series.sort_values(kind="mergesort").index
    X_sorted = X.iloc[order].reset_index(drop=True)
    y_sorted = y.iloc[order].reset_index(drop=True)
    date_series = date_series.iloc[order].reset_index(drop=True)
    text_sorted = text_sorted.iloc[order].reset_index(drop=True)

    unique_dates = pd.Series(date_series.drop_duplicates().tolist())
    if len(unique_dates) <= n_splits:
        raise ValueError(
            f"Need more than {n_splits} unique trade dates for panel CV; got {len(unique_dates)}."
        )

    tss = TimeSeriesSplit(n_splits=n_splits)
    fold_aucs: List[float] = []
    fold_accuracies: List[float] = []
    oof_frames: List[pd.DataFrame] = []

    start_time = time.time()
    for train_idx, test_idx in tss.split(unique_dates):
        train_dates = unique_dates.iloc[train_idx]
        test_dates = unique_dates.iloc[test_idx]

        train_mask = date_series.isin(train_dates)
        test_mask = date_series.isin(test_dates)
        X_train_num = X_sorted.loc[train_mask]
        y_train = y_sorted.loc[train_mask]
        X_test_num = X_sorted.loc[test_mask]
        y_test = y_sorted.loc[test_mask]
        train_text = text_sorted.loc[train_mask]
        test_text = text_sorted.loc[test_mask]

        X_train_text, X_test_text, _ = fit_text_svd_features(
            train_text,
            test_text,
            n_components=text_n_components,
        )
        X_train = _combine_feature_frames(X_train_num, X_train_text)
        X_test = _combine_feature_frames(
            X_test_num, X_test_text if X_test_text is not None else X_train_text.iloc[0:0]
        )

        model = _fit_lightgbm_classifier(X_train, y_train, categorical_features)

        y_pred = model.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))
        fold_accuracies.append(acc)

        try:
            proba = model.predict_proba(X_test)[:, 1]
        except Exception:
            proba = np.full(len(X_test), np.nan)

        auc = _safe_binary_auc(y_test, proba)
        fold_aucs.append(auc)
        oof_frames.append(
            _build_panel_oof_frame(
                X_test_num,
                y_test,
                date_series.loc[test_mask],
                y_pred,
                proba,
            )
        )

    if not fold_accuracies:
        raise ValueError("Panel TimeSeriesSplit produced no folds.")

    X_full_text, _, text_artifacts = fit_text_svd_features(
        text_sorted,
        None,
        n_components=text_n_components,
    )
    X_full = _combine_feature_frames(X_sorted, X_full_text)
    model = _fit_lightgbm_classifier(X_full, y_sorted, categorical_features)
    training_time_seconds = time.time() - start_time

    mean_auc = float(np.nanmean(fold_aucs))
    mean_accuracy = float(np.mean(fold_accuracies))
    oof_frame = pd.concat(oof_frames, ignore_index=True) if oof_frames else pd.DataFrame()
    per_ticker_auc, per_ticker_accuracy, per_ticker_eval_rows, per_ticker_auc_unavailable = (
        _summarize_panel_symbol_metrics(oof_frame)
    )

    metrics: Dict[str, float | str | List[float] | int] = {
        "mean_auc": mean_auc,
        "mean_accuracy": mean_accuracy,
        "fold_aucs": fold_aucs,
        "fold_accuracies": fold_accuracies,
        "train_test_split": f"PanelTimeSeriesSplit_n{n_splits}",
        "cv_unit": "trade_date",
        "n_rows": int(len(X_sorted)),
        "n_unique_dates": int(len(unique_dates)),
        "text_svd_components": int(text_n_components),
        "accuracy": mean_accuracy,
        "auc": mean_auc,
        "training_time_seconds": training_time_seconds,
    }
    if per_ticker_eval_rows:
        metrics["per_ticker_auc"] = per_ticker_auc
        metrics["per_ticker_accuracy"] = per_ticker_accuracy
        metrics["per_ticker_eval_rows"] = per_ticker_eval_rows
        if per_ticker_auc_unavailable:
            metrics["per_ticker_auc_unavailable"] = per_ticker_auc_unavailable
    return model, metrics, text_artifacts, X_full


def predict_proba_latest(model: LGBMClassifier, X: pd.DataFrame) -> float:
    """Return the predicted probability of the positive class for the latest row.

    This utility is intended to be called after training, using the full
    feature matrix or a single-row inference frame. It extracts the last row in
    ``X`` and returns the model's probability estimate for the positive class
    (``y = 1``).

    Args:
        model: A trained LightGBM classifier.
        X: Full feature matrix used during training, with at least one row.

    Returns:
        A float in ``[0, 1]`` representing the model's estimated probability
        of the positive class for the latest row.

    Raises:
        ValueError: If ``X`` is empty.
    """

    if X.empty:
        raise ValueError("Feature matrix X is empty; cannot compute prediction.")

    latest_row = X.iloc[[-1]]
    proba = model.predict_proba(latest_row)[0, 1]
    # Ensure the value is a plain Python float for JSON serialization.
    return float(proba)
