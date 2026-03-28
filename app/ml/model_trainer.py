from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

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


def train_lightgbm(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
) -> Tuple[LGBMClassifier, Dict[str, float | str | List[float]]]:
    """Train LightGBM with time-series cross-validation and return last-fold model.

    Uses ``TimeSeriesSplit(n_splits)`` so each fold trains on past data and
    evaluates on future data. Aggregates out-of-sample AUC and accuracy across
    folds and returns the model trained in the last fold (for SHAP and
    predict_proba_latest).

    Args:
        X: Feature matrix, rows ordered in time (oldest first).
        y: Binary target aligned with ``X``.
        n_splits: Number of time-series splits (default 5).

    Returns:
        (model, metrics) where model is the last-fold trained LGBMClassifier
        and metrics includes mean_auc, mean_accuracy, fold_aucs, fold_accuracies,
        train_test_split, and backward-compatible accuracy/auc keys.
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
    model: LGBMClassifier | None = None

    for train_idx, test_idx in tss.split(X):
        X_train = X.iloc[train_idx]
        y_train = y.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_test = y.iloc[test_idx]

        clf = LGBMClassifier(**LGBM_PARAMS)
        clf.fit(X_train, y_train)
        model = clf

        y_pred = model.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))
        fold_accuracies.append(acc)

        try:
            proba = model.predict_proba(X_test)[:, 1]
            auc = float(roc_auc_score(y_test, proba))
        except Exception:
            auc = float("nan")
        fold_aucs.append(auc)

    if model is None:
        raise ValueError("TimeSeriesSplit produced no folds.")

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
    }
    return model, metrics


def predict_proba_latest(model: LGBMClassifier, X: pd.DataFrame) -> float:
    """Return the predicted probability of an upward move for the latest row.

    This utility is intended to be called after training, using the full
    feature matrix (including both train and test periods). It extracts the
    last row in ``X`` and returns the model's probability estimate for the
    positive class (``y = 1``), which corresponds to
    ``\"next day close > today close\"`` in this project.

    Args:
        model: A trained LightGBM classifier.
        X: Full feature matrix used during training, with at least one row.

    Returns:
        A float in ``[0, 1]`` representing the model's estimated probability
        that the next day's return is positive.

    Raises:
        ValueError: If ``X`` is empty.
    """

    if X.empty:
        raise ValueError("Feature matrix X is empty; cannot compute prediction.")

    latest_row = X.iloc[[-1]]
    proba = model.predict_proba(latest_row)[0, 1]
    # Ensure the value is a plain Python float for JSON serialization.
    return float(proba)
