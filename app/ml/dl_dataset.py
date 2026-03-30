"""Time-series dataset with sliding window and fold-isolated scaling.

Provides TimeSeriesDataset for PyTorch DataLoader and prepare_dl_data for
fold-isolated feature scaling with lookback mechanism for test sets.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler
from torch.utils.data import Dataset

from app.ml.dl_config import COLUMNS_TO_SCALE, PASSTHROUGH_COLUMNS, DLConfig

logger = logging.getLogger(__name__)


class TimeSeriesDataset(Dataset):
    """Time-series dataset with sliding window support.

    Handles train/test mode differently to support lookback mechanism:
    - Train mode: X and y same length, window [t-14:t] predicts y[t]
    - Test mode: X includes lookback (longer than y), window alignment adjusted

    Args:
        X: Feature matrix (n_samples, n_features)
        y: Binary labels (n_samples,), already shifted by -1 in feature engineering
        seq_len: Sliding window size in days
        is_test: Whether this is test set (affects label alignment)
    """

    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        seq_len: int = 15,
        is_test: bool = False,
    ):
        self.X = X
        self.y = y
        self.seq_len = seq_len
        self.is_test = is_test

    def __len__(self) -> int:
        if self.is_test:
            return len(self.y)
        else:
            return len(self.X) - self.seq_len + 1

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        if self.is_test:
            # Test mode: X includes lookback, idx=0 corresponds to X[0:15]
            X_seq = self.X[idx : idx + self.seq_len]
            y_label = self.y[idx]
        else:
            # Train mode: window [idx:idx+seq_len], label at window end
            X_seq = self.X[idx : idx + self.seq_len]
            y_label = self.y[idx + self.seq_len - 1]

        return (
            torch.FloatTensor(X_seq),
            torch.FloatTensor([y_label]),
        )


def prepare_dl_data(
    X: pd.DataFrame,
    y: pd.Series,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    config: DLConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Prepare data for a single TimeSeriesSplit fold with fold-isolated scaling.

    Critical design:
    1. Scaler only fits on train set (prevents data leakage)
    2. Test set borrows seq_len-1 days from train end as lookback
    3. Feature grouping: COLUMNS_TO_SCALE normalized, PASSTHROUGH_COLUMNS as-is

    Args:
        X: Full feature matrix
        y: Full labels (already shifted by -1)
        train_idx: Training set indices
        test_idx: Test set indices
        config: DL configuration

    Returns:
        (X_train_scaled, X_test_scaled, y_train, y_test)
        - X_test_scaled includes lookback (length = len(test_idx) + seq_len - 1)
        - y_test does NOT include lookback (length = len(test_idx))

    Raises:
        ValueError: If train set too small to provide lookback
    """
    # Split train/test
    X_train = X.iloc[train_idx].copy()
    y_train = y.iloc[train_idx].values

    # Test set with lookback
    lookback_len = config.seq_len - 1
    first_test_idx = test_idx[0]

    if first_test_idx < lookback_len:
        raise ValueError(
            f"训练集数据量不足：当前训练集仅有 {first_test_idx} 个样本，"
            f"无法为测试集提供 {lookback_len} 天的历史回溯窗口。"
            f"请检查 TimeSeriesSplit 的 n_splits 设置或增加数据量。"
        )

    # Extend test indices with lookback
    extended_test_idx = list(range(first_test_idx - lookback_len, first_test_idx)) + list(
        test_idx
    )
    X_test_extended = X.iloc[extended_test_idx].copy()
    y_test = y.iloc[test_idx].values

    # Initialize scaler
    if config.scaler_type == "robust":
        scaler = RobustScaler()
    elif config.scaler_type == "standard":
        scaler = StandardScaler()
    elif config.scaler_type == "minmax":
        scaler = MinMaxScaler()
    else:
        raise ValueError(f"Unknown scaler_type: {config.scaler_type}")

    # Feature grouping
    scale_cols = [c for c in COLUMNS_TO_SCALE if c in X_train.columns]
    pass_cols = [c for c in PASSTHROUGH_COLUMNS if c in X_train.columns]

    # Fold-isolated scaling
    X_train_scaled = X_train.copy()
    X_test_scaled = X_test_extended.copy()

    if scale_cols:
        X_train_scaled[scale_cols] = scaler.fit_transform(X_train[scale_cols])
        X_test_scaled[scale_cols] = scaler.transform(X_test_extended[scale_cols])

    # Ensure column order consistency
    all_cols = scale_cols + pass_cols
    X_train_scaled = X_train_scaled[all_cols].values
    X_test_scaled = X_test_scaled[all_cols].values

    return X_train_scaled, X_test_scaled, y_train, y_test
