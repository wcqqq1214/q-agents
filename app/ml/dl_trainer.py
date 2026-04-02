"""Deep learning trainer with TimeSeriesSplit and early stopping"""

from __future__ import annotations

import copy
import logging
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader

from app.ml.dl_config import DLConfig, set_seed
from app.ml.dl_dataset import TimeSeriesDataset, prepare_dl_data
from app.ml.dl_models import create_model

logger = logging.getLogger(__name__)


def train_dl_model(
    X: pd.DataFrame,
    y: pd.Series,
    config: DLConfig | None = None,
) -> Tuple[nn.Module, Dict[str, float | str | List[float]], object]:
    """Train deep learning model with TimeSeriesSplit and early stopping

    Training flow:
    1. TimeSeriesSplit(n_splits) for time-series cross-validation
    2. Each fold:
       - Split train into 85% actual_train + 15% validation
       - prepare_dl_data: fold-isolated scaling + lookback
       - Training loop: AdamW + weighted BCE + gradient clipping
       - Early stopping on validation loss with best weight rollback
       - Learning rate scheduling with ReduceLROnPlateau
    3. Return last fold's model + aggregated metrics + scaler

    Args:
        X: Feature matrix (from features.py FEATURE_COLS)
        y: Binary labels (already shifted by -1)
        config: DL configuration, defaults to DLConfig()

    Returns:
        (model, metrics, scaler)
        - model: Last fold's trained model
        - metrics: Compatible with LightGBM format
        - scaler: RobustScaler from last fold (for inference)

    Raises:
        ValueError: If X or y is empty, or if lengths don't match
    """
    if config is None:
        config = DLConfig()

    if X.empty or y.empty:
        raise ValueError("Feature matrix X or target y is empty.")
    if len(X) != len(y):
        raise ValueError("X and y must have the same number of rows.")
    if X.isna().any().any():
        raise ValueError("Feature matrix X contains NaN values.")
    numeric_values = X.to_numpy(dtype=float, copy=False)
    if not np.isfinite(numeric_values).all():
        raise ValueError("Feature matrix X contains non-finite values.")

    tss = TimeSeriesSplit(n_splits=config.n_splits)
    fold_aucs: List[float] = []
    fold_accuracies: List[float] = []
    model: nn.Module | None = None
    last_fold_scaler: object | None = None

    start_time = time.time()

    for fold_idx, (train_idx, test_idx) in enumerate(tss.split(X)):
        logger.info(f"Training fold {fold_idx + 1}/{config.n_splits}")

        # Fix seed for reproducible initialization across folds
        set_seed(42)

        # Split train into actual_train (85%) + validation (15%)
        train_size = int(len(train_idx) * 0.85)
        actual_train_idx = train_idx[:train_size]
        val_idx = train_idx[train_size:]

        # Prepare data with fold-isolated scaling
        X_train, X_val, y_train, y_val, train_scaler = prepare_dl_data(
            X, y, actual_train_idx, val_idx, config
        )
        X_test_scaled, _, y_test, _, _ = prepare_dl_data(
            X, y, train_idx, test_idx, config
        )

        # Save the last fold's scaler for inference
        last_fold_scaler = train_scaler

        # Create datasets
        train_dataset = TimeSeriesDataset(
            X_train, y_train, seq_len=config.seq_len, is_test=False
        )
        val_dataset = TimeSeriesDataset(
            X_val, y_val, seq_len=config.seq_len, is_test=True
        )
        test_dataset = TimeSeriesDataset(
            X_test_scaled, y_test, seq_len=config.seq_len, is_test=True
        )

        # Create dataloaders
        train_loader = DataLoader(
            train_dataset, batch_size=config.batch_size, shuffle=True, drop_last=True, pin_memory=True
        )
        val_loader = DataLoader(
            val_dataset, batch_size=config.batch_size, shuffle=False, drop_last=True, pin_memory=True
        )
        test_loader = DataLoader(
            test_dataset, batch_size=config.batch_size, shuffle=False, drop_last=True, pin_memory=True
        )

        # Create model
        input_size = X_train.shape[1]
        model = create_model(input_size, config)
        model = model.to(config.device)

        # Weighted BCE loss for class imbalance
        num_positives = (y_train == 1).sum()
        num_negatives = (y_train == 0).sum()
        pos_weight_val = num_negatives / max(num_positives, 1)
        pos_weight = torch.tensor([pos_weight_val], dtype=torch.float32).to(config.device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        # AdamW optimizer
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )

        # Learning rate scheduler
        scheduler = ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=0.5,
            patience=5,
        )

        # Early stopping with best weight rollback
        best_val_loss = float("inf")
        patience_counter = 0
        best_model_wts = copy.deepcopy(model.state_dict())

        for epoch in range(config.max_epochs):
            # Training phase
            model.train()
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(config.device)
                y_batch = y_batch.to(config.device)

                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()

                # Gradient clipping
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation phase
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(config.device)
                    y_batch = y_batch.to(config.device)

                    logits = model(X_batch)
                    loss = criterion(logits, y_batch)
                    val_loss += loss.item()

            # Handle empty validation set
            if len(val_loader) > 0:
                val_loss /= len(val_loader)
            else:
                val_loss = float("inf")

            # Learning rate scheduling
            scheduler.step(val_loss)

            # Early stopping check + best weight saving
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_model_wts = copy.deepcopy(model.state_dict())
            else:
                patience_counter += 1
                if patience_counter >= config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch + 1}")
                    break

        # Rollback to best weights
        model.load_state_dict(best_model_wts)

        # Fold evaluation on test set
        model.eval()
        y_pred_list = []
        y_proba_list = []
        y_test_list = []

        with torch.no_grad():
            for batch_idx, (X_batch, y_batch) in enumerate(test_loader):
                X_batch = X_batch.to(config.device)
                logits = model(X_batch)
                proba = torch.sigmoid(logits).cpu().numpy().flatten()
                pred = (proba > 0.5).astype(int)

                y_pred_list.extend(pred)
                y_proba_list.extend(proba)
                y_test_list.extend(y_batch.numpy().flatten())

        y_pred = np.array(y_pred_list)
        y_proba = np.array(y_proba_list)
        y_test = np.array(y_test_list)

        # Calculate metrics
        acc = float(accuracy_score(y_test, y_pred))
        fold_accuracies.append(acc)

        try:
            auc = float(roc_auc_score(y_test, y_proba))
        except Exception as exc:
            logger.warning(
                "Fold %s AUC unavailable: %s",
                fold_idx + 1,
                exc,
            )
            auc = float("nan")
        fold_aucs.append(auc)

        logger.info(f"Fold {fold_idx + 1} - Accuracy: {acc:.4f}, AUC: {auc:.4f}")

    if model is None:
        raise ValueError("TimeSeriesSplit produced no folds.")

    # Calculate total training time
    training_time_seconds = time.time() - start_time

    # Aggregate metrics
    finite_fold_aucs = [auc for auc in fold_aucs if np.isfinite(auc)]
    mean_auc = float(np.mean(finite_fold_aucs)) if finite_fold_aucs else float("nan")
    mean_accuracy = float(np.mean(fold_accuracies))

    metrics: Dict[str, float | str | List[float]] = {
        "mean_auc": mean_auc,
        "mean_accuracy": mean_accuracy,
        "fold_aucs": fold_aucs,
        "fold_accuracies": fold_accuracies,
        "train_test_split": f"TimeSeriesSplit_n{config.n_splits}",
        "model_type": config.model_type,
        "seq_len": config.seq_len,
        # Backward compatibility
        "accuracy": mean_accuracy,
        "auc": mean_auc,
        "training_time_seconds": training_time_seconds,
    }

    return model, metrics, last_fold_scaler
