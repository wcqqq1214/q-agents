"""Standalone CLI script for LightGBM report generation.

This script trains the panel LightGBM model on the database-backed feature
pipeline, generates a report, and exports it as a Markdown file.

Usage:
    uv run python scripts/ml/compare_models.py --symbol AAPL --start 2024-01-01 --end 2024-12-31
    uv run python scripts/ml/compare_models.py --symbol NVDA --start 2024-01-01 --end 2024-12-31 --output /tmp/nvda_report.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from app.ml.features import FEATURE_COLS, build_features
    from app.ml.model_registry import (
        format_comparison_markdown,
        generate_comparison_report,
        train_all_models,
    )
except ImportError as e:
    raise ImportError(
        f"Failed to import app.ml modules: {e}\n"
        "This may indicate that the database or Python dependencies are unavailable.\n"
        "Please ensure:\n"
        "  1. All dependencies are installed (uv pip install -e .)\n"
        "  2. The local database has been initialized and populated"
    ) from e


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Train the panel LightGBM model and generate a Markdown report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python scripts/ml/compare_models.py --symbol AAPL --start 2024-01-01 --end 2024-12-31
    uv run python scripts/ml/compare_models.py --symbol TSLA --start 2023-01-01 --end 2024-12-31 --output /tmp/tsla_report.md
        """,
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Stock ticker symbol (e.g., AAPL, NVDA, BTC-USD)",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for markdown file (default: data/reports/model_comparison_{symbol}.md)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def validate_date(date_str: str) -> datetime:
    """Validate and parse date string."""

    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}': expected YYYY-MM-DD") from e


def load_features(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Load and prepare DB-backed features for a single symbol."""

    logger.info(
        "Loading DB features for %s from %s to %s",
        symbol,
        start_date.date(),
        end_date.date(),
    )

    data = build_features(
        symbol,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
    )
    if data.empty:
        raise ValueError(f"No feature rows returned for {symbol} in the requested date range")

    data = data.dropna(subset=["target_up_big_move_t3"]).reset_index(drop=True)
    if data.empty or len(data) < 50:
        raise ValueError(
            f"Insufficient labeled feature rows after filtering: {len(data)} rows. "
            f"Need at least 50 rows for panel training."
        )

    X = data[FEATURE_COLS]
    y = data["target_up_big_move_t3"].astype(int)

    logger.info("Built feature matrix: X.shape=%s, y.shape=%s", X.shape, y.shape)
    logger.info("Positive class ratio: %.4f", y.mean())
    return data, X, y


def determine_output_path(symbol: str, custom_path: str | None) -> Path:
    """Determine output file path."""

    if custom_path:
        return Path(custom_path)

    base_dir = Path("data/reports")
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"model_comparison_{symbol.upper()}.md"


def main() -> int:
    """Main entry point for the compare_models script."""

    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        start_date = validate_date(args.start)
        end_date = validate_date(args.end)
    except ValueError as e:
        logger.error("Date validation error: %s", e)
        return 1

    if start_date >= end_date:
        logger.error("Start date must be before end date: %s >= %s", args.start, args.end)
        return 1

    logger.info("Running LightGBM report for %s", args.symbol.upper())
    logger.info("Date range: %s to %s", args.start, args.end)

    try:
        data, X, _ = load_features(args.symbol.upper(), start_date, end_date)
    except ValueError as e:
        logger.error("Feature loading failed: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error during feature loading: %s", e, exc_info=True)
        return 1

    try:
        logger.info("Training LightGBM...")
        results = train_all_models(
            symbol=args.symbol.upper(),
            model_types=["lightgbm"],
            start_date=args.start,
            end_date=args.end,
        )
        logger.info("Trained models: %s", list(results.keys()))
    except ValueError as e:
        logger.error("Model training failed: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error during model training: %s", e, exc_info=True)
        return 1

    try:
        logger.info("Generating report...")
        report = generate_comparison_report(
            results=results,
            symbol=args.symbol.upper(),
            date_range=(args.start, args.end),
            X=X,
        )
    except ValueError as e:
        logger.error("Report generation failed: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error during report generation: %s", e, exc_info=True)
        return 1

    try:
        markdown = format_comparison_markdown(report)
        output_path = determine_output_path(args.symbol, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        logger.info("Report written to: %s", output_path)
    except Exception as e:
        logger.error("Failed to format or write report: %s", e, exc_info=True)
        return 1

    pred = report["predictions"]["lightgbm"]
    auc = report["metrics"]["lightgbm"].get("mean_auc", "N/A")
    signal = "UP" if isinstance(pred, float) and pred > 0.5 else "DOWN"

    print("\n" + "=" * 60)
    print("LIGHTGBM SUMMARY")
    print("=" * 60)
    print(f"Symbol: {args.symbol.upper()}")
    print(f"Date Range: {args.start} to {args.end}")
    print(f"Data Points: {len(data)}")
    print("-" * 60)
    print(f"Prediction: {pred:.4f} ({signal})")
    if isinstance(auc, float):
        print(f"Mean AUC: {auc:.4f}")
    else:
        print(f"Mean AUC: {auc}")
    print("=" * 60)
    print(f"\nFull report saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
