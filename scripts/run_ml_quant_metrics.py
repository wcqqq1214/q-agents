"""Run ML quant pipeline and print/validate Accuracy and AUC.

验证思路（How to verify accuracy and AUC）:
-----------------------------------------
1. 数据与划分：使用 load_ohlcv_with_macro + build_dataset 得到 (X, y)；
   train_lightgbm 内部用 TimeSeriesSplit(n_splits=5) 做滚动验证，不泄露未来数据。
2. 指标来源：每个 fold 在「未参与训练」的测试段上计算 accuracy 和 roc_auc；
   汇总为 mean_accuracy、mean_auc 以及 fold_aucs / fold_accuracies。
3. 本脚本：对指定 ticker(s) 跑完整流程，打印上述指标；可选地做阈值检查（如 AUC > 0.52）。

默认标的池（v3 Alpha 核心池）：NVDA, MSFT, TSLA, AAPL, GOOG, META, AMZN, AMD, TSM。
已移除：CRCL（样本不足）、SNDK（退市/被收购）、QQQ/VOO（宽基指数，暂不测）。

运行方式:
  uv run python -m tests.run_ml_quant_metrics              # 默认跑 Alpha 核心池 9 只
  uv run python -m tests.run_ml_quant_metrics NVDA META   # 指定标的
  uv run python -m tests.run_ml_quant_metrics --check      # 打印并检查 AUC/Accuracy 下限
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from app.ml.feature_engine import build_dataset, load_ohlcv_with_macro
from app.ml.model_trainer import train_lightgbm

# v3 Alpha core pool (no CRCL, SNDK, QQQ, VOO).
ALPHA_CORE_TICKERS = [
    "NVDA",
    "MSFT",
    "TSLA",
    "AAPL",
    "GOOG",
    "META",
    "AMZN",
    "AMD",
    "TSM",
]


def run_one(ticker: str) -> dict:
    """Run pipeline for one ticker; return metrics dict (and optional model/X/y)."""
    df = load_ohlcv_with_macro(ticker.strip().upper(), period_years=5)
    X, y = build_dataset(df)
    model, metrics = train_lightgbm(X, y, n_splits=5)
    return {
        "ticker": ticker,
        "n_samples": len(X),
        "pos_ratio": float(y.mean()),
        "mean_accuracy": metrics["mean_accuracy"],
        "mean_auc": metrics["mean_auc"],
        "fold_aucs": metrics["fold_aucs"],
        "fold_accuracies": metrics["fold_accuracies"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ML quant pipeline and print Accuracy / AUC (TimeSeriesSplit 5-fold)."
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        default=ALPHA_CORE_TICKERS,
        help="US equity ticker(s). Default: NVDA, MSFT, TSLA, AAPL, GOOG, META, AMZN, AMD, TSM",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with non-zero if any ticker has mean_auc < 0.52 (AUC-only; accuracy not used)",
    )
    args = parser.parse_args()
    tickers: List[str] = [t for t in args.tickers if t and not t.startswith("-")]
    if not tickers:
        tickers = ALPHA_CORE_TICKERS

    failed: List[str] = []
    for ticker in tickers:
        print(f"\n=== {ticker} ===")
        try:
            out = run_one(ticker)
        except Exception as e:
            print(f"  Error: {e}")
            failed.append(ticker)
            continue
        print(f"  n_samples: {out['n_samples']}, pos_ratio: {out['pos_ratio']:.4f}")
        print(f"  mean_accuracy: {out['mean_accuracy']:.4f}")
        print(f"  mean_auc:      {out['mean_auc']:.4f}")
        print(f"  fold_aucs:     {[round(a, 4) for a in out['fold_aucs']]}")
        print(f"  fold_accs:     {[round(a, 4) for a in out['fold_accuracies']]}")
        for i, fa in enumerate(out["fold_aucs"]):
            if fa == 0.5:
                print(f"  Warning: Fold {i + 1} AUC is 0.5, likely due to data starvation.")
        if args.check:
            if out["mean_auc"] < 0.52:
                failed.append(ticker)
                print("  -> FAILED check (mean_auc >= 0.52)")
            else:
                print("  -> check passed")

    if failed:
        print(f"\nFailed tickers: {failed}")
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
