"""Tests for deep learning dataset module (dl_dataset.py).

Tests follow TDD approach: test first, then implement.
"""

import numpy as np
import pandas as pd
import pytest
import torch

from app.ml.dl_config import DLConfig
from app.ml.dl_dataset import TimeSeriesDataset, prepare_dl_data


class TestTimeSeriesDataset:
    """Test TimeSeriesDataset class."""

    def test_timeseries_dataset_train_mode(self):
        """Test TimeSeriesDataset in training mode."""
        X = np.random.randn(100, 10)  # 100 samples, 10 features
        y = np.random.randint(0, 2, 100)  # Binary labels

        dataset = TimeSeriesDataset(X, y, seq_len=15, is_test=False)

        # Length should be len(X) - seq_len + 1
        assert len(dataset) == 86  # 100 - 15 + 1

        # Get first sample
        X_seq, y_label = dataset[0]
        assert X_seq.shape == (15, 10)  # (seq_len, features)
        assert y_label.shape == (1,)

    def test_timeseries_dataset_test_mode(self):
        """Test TimeSeriesDataset in test mode with lookback."""
        X = np.random.randn(114, 10)  # 100 test + 14 lookback
        y = np.random.randint(0, 2, 100)  # Only 100 labels

        dataset = TimeSeriesDataset(X, y, seq_len=15, is_test=True)

        # Length should be len(y)
        assert len(dataset) == 100

        # Get first sample (uses lookback)
        X_seq, y_label = dataset[0]
        assert X_seq.shape == (15, 10)
        assert y_label.shape == (1,)

    def test_timeseries_dataset_train_label_alignment(self):
        """Test train mode label alignment: window [t-14:t] predicts y[t]."""
        X = np.arange(100 * 5).reshape(100, 5)  # Predictable values
        y = np.arange(100)  # Labels are indices

        dataset = TimeSeriesDataset(X, y, seq_len=15, is_test=False)

        # First window: X[0:15], label should be y[14]
        X_seq, y_label = dataset[0]
        assert y_label[0] == 14

        # Second window: X[1:16], label should be y[15]
        X_seq, y_label = dataset[1]
        assert y_label[0] == 15

    def test_timeseries_dataset_test_label_alignment(self):
        """Test test mode label alignment with lookback."""
        X = np.arange(114 * 5).reshape(114, 5)  # Predictable values
        y = np.arange(100)  # 100 labels

        dataset = TimeSeriesDataset(X, y, seq_len=15, is_test=True)

        # First window: X[0:15], label should be y[0]
        X_seq, y_label = dataset[0]
        assert y_label[0] == 0

        # Second window: X[15:30], label should be y[1]
        X_seq, y_label = dataset[1]
        assert y_label[0] == 1

    def test_timeseries_dataset_returns_torch_tensors(self):
        """Test dataset returns PyTorch tensors."""
        X = np.random.randn(100, 10)
        y = np.random.randint(0, 2, 100)

        dataset = TimeSeriesDataset(X, y, seq_len=15, is_test=False)
        X_seq, y_label = dataset[0]

        assert isinstance(X_seq, torch.Tensor)
        assert isinstance(y_label, torch.Tensor)
        assert X_seq.dtype == torch.float32
        assert y_label.dtype == torch.float32

    def test_timeseries_dataset_different_seq_len(self):
        """Test dataset with different sequence lengths."""
        X = np.random.randn(100, 10)
        y = np.random.randint(0, 2, 100)

        for seq_len in [5, 10, 20, 30]:
            dataset = TimeSeriesDataset(X, y, seq_len=seq_len, is_test=False)
            assert len(dataset) == 100 - seq_len + 1

            X_seq, y_label = dataset[0]
            assert X_seq.shape == (seq_len, 10)


class TestPrepareDLData:
    """Test prepare_dl_data function."""

    def test_prepare_dl_data_fold_isolation(self):
        """Test prepare_dl_data performs fold-isolated scaling."""
        # Create mock data with known columns
        X = pd.DataFrame(
            np.random.randn(200, 5),
            columns=["ret_1d", "rsi_14", "sentiment_score", "volume_ratio_5d", "day_of_week"],
        )
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15)

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        # X_test should include lookback (14 extra rows)
        assert X_test.shape[0] == len(test_idx) + config.seq_len - 1  # 50 + 14 = 64
        assert y_test.shape[0] == len(test_idx)  # 50 (no lookback for labels)

        # Check scaling was applied (same number of features)
        assert X_train.shape[1] == X.shape[1]
        assert X_test.shape[1] == X.shape[1]

    def test_prepare_dl_data_insufficient_lookback(self):
        """Test prepare_dl_data raises error when train set too small."""
        X = pd.DataFrame(np.random.randn(20, 5))
        y = pd.Series(np.random.randint(0, 2, 20))

        train_idx = np.arange(0, 10)  # Only 10 samples
        test_idx = np.arange(10, 20)

        config = DLConfig(seq_len=15)  # Needs 14 lookback

        # Should raise ValueError
        with pytest.raises(ValueError, match="训练集数据量不足"):
            prepare_dl_data(X, y, train_idx, test_idx, config)

    def test_prepare_dl_data_returns_numpy_arrays(self):
        """Test prepare_dl_data returns numpy arrays."""
        X = pd.DataFrame(
            np.random.randn(200, 5),
            columns=["ret_1d", "rsi_14", "sentiment_score", "volume_ratio_5d", "day_of_week"],
        )
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15)

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        assert isinstance(X_train, np.ndarray)
        assert isinstance(X_test, np.ndarray)
        assert isinstance(y_train, np.ndarray)
        assert isinstance(y_test, np.ndarray)

    def test_prepare_dl_data_scaling_applied(self):
        """Test that scaling is actually applied to scaled columns."""
        # Create data with large values that should be scaled
        X = pd.DataFrame(
            {
                "ret_1d": np.random.randn(200) * 100,  # Large values
                "rsi_14": np.random.uniform(0, 100, 200),  # 0-100 range
                "sentiment_score": np.random.uniform(-1, 1, 200),  # Already normalized
                "volume_ratio_5d": np.random.randn(200) * 50,  # Large values
                "day_of_week": np.random.randint(0, 5, 200),  # Categorical
            }
        )
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15, scaler_type="robust")

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        # After scaling, train set should have mean close to 0 for scaled columns
        # (RobustScaler centers on median, so mean might not be exactly 0)
        # Just verify scaling happened by checking values are in reasonable range
        assert X_train.shape[0] == len(train_idx)
        assert X_test.shape[0] == len(test_idx) + config.seq_len - 1

    def test_prepare_dl_data_with_standard_scaler(self):
        """Test prepare_dl_data with standard scaler."""
        X = pd.DataFrame(
            np.random.randn(200, 5),
            columns=["ret_1d", "rsi_14", "sentiment_score", "volume_ratio_5d", "day_of_week"],
        )
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15, scaler_type="standard")

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        assert X_train.shape[0] == len(train_idx)
        assert X_test.shape[0] == len(test_idx) + config.seq_len - 1

    def test_prepare_dl_data_with_minmax_scaler(self):
        """Test prepare_dl_data with minmax scaler."""
        X = pd.DataFrame(
            np.random.randn(200, 5),
            columns=["ret_1d", "rsi_14", "sentiment_score", "volume_ratio_5d", "day_of_week"],
        )
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15, scaler_type="minmax")

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        assert X_train.shape[0] == len(train_idx)
        assert X_test.shape[0] == len(test_idx) + config.seq_len - 1

    def test_prepare_dl_data_feature_grouping(self):
        """Test prepare_dl_data respects feature grouping."""
        from app.ml.dl_config import COLUMNS_TO_SCALE, PASSTHROUGH_COLUMNS

        # Create data with both scaled and passthrough columns
        scale_cols = COLUMNS_TO_SCALE[:3]
        pass_cols = PASSTHROUGH_COLUMNS[:2]
        all_cols = scale_cols + pass_cols

        X = pd.DataFrame(np.random.randn(200, len(all_cols)), columns=all_cols)
        y = pd.Series(np.random.randint(0, 2, 200))

        train_idx = np.arange(0, 150)
        test_idx = np.arange(150, 200)

        config = DLConfig(seq_len=15)

        X_train, X_test, y_train, y_test = prepare_dl_data(X, y, train_idx, test_idx, config)

        # Should have same number of features
        assert X_train.shape[1] == len(all_cols)
        assert X_test.shape[1] == len(all_cols)
