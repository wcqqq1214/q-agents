"""Standalone CLI script for multi-model comparison.

This script trains multiple ML models (LightGBM, GRU, LSTM) on stock data,
generates a comparison report, and exports it as a Markdown file.

Usage:
    uv run python scripts/ml/compare_models.py --symbol AAPL --start 2024-01-01 --end 2024-12-31
    uv run python scripts/ml/compare_models.py --symbol NVDA --start 2024-01-01 --end 2024-12-31 --models lightgbm,gru --output /tmp/nvda_comparison.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to path for imports
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd

# Import ML modules with error handling
try:
    # Import feature engineering functions
    from app.ml.feature_engine import build_dataset, load_ohlcv_with_macro, FeatureConfig

    # Import model registry functions
    from app.ml.model_registry import (
        generate_comparison_report,
        format_comparison_markdown,
        train_all_models,
    )

    # Import DL config for deep learning models
    from app.ml.dl_config import DLConfig

    # Import feature columns
    from app.ml.features import FEATURE_COLS
except ImportError as e:
    raise ImportError(
        f"Failed to import app.ml modules: {e}\n"
        "This may indicate that MCP servers are not running or dependencies are missing.\n"
        "Please ensure:\n"
        "  1. MCP servers are running (bash scripts/startup/start_mcp_servers.sh)\n"
        "  2. All dependencies are installed (uv pip install -e .)"
    ) from e


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Train multiple ML models and generate a comparison report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Default: train LightGBM, GRU, LSTM on AAPL data from 2024
    uv run python scripts/ml/compare_models.py --symbol AAPL --start 2024-01-01 --end 2024-12-31

    # Train only LightGBM
    uv run python scripts/ml/compare_models.py --symbol NVDA --start 2024-01-01 --end 2024-12-31 --models lightgbm

    # Custom output path
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
        "--models",
        type=str,
        default="lightgbm,gru,lstm",
        help="Comma-separated list of models to train (default: lightgbm,gru,lstm)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def validate_date(date_str: str) -> datetime:
    """Validate and parse date string.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Parsed datetime object

    Raises:
        ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}': expected YYYY-MM-DD") from e


def load_features(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Load and prepare features from OHLCV data.

    Args:
        symbol: Stock ticker symbol
        start_date: Start date for data retrieval
        end_date: End date for data retrieval

    Returns:
        Tuple of (X, y) - feature matrix and target series

    Raises:
        ValueError: If insufficient data or date range invalid
    """
    logger.info(f"Loading OHLCV data for {symbol} from {start_date.date()} to {end_date.date()}")

    # Calculate years needed for yfinance (need extra buffer for feature computation)
    delta_days = (end_date - start_date).days
    period_years = max(5, (delta_days // 365) + 1)  # At least 5 years for training

    # Load OHLCV with macro data (includes DXY, VIX)
    df = load_ohlcv_with_macro(symbol, period_years=period_years)

    if df.empty:
        raise ValueError(f"No OHLCV data returned for {symbol}")

    logger.info(f"Loaded {len(df)} rows of raw data")

    # Filter to requested date range
    df = df.loc[start_date:end_date].copy()

    if len(df) < 100:
        raise ValueError(
            f"Insufficient data after date filtering: {len(df)} rows. "
            f"Need at least 100 rows for meaningful training."
        )

    logger.info(f"After date filter: {len(df)} rows")

    # Build features using feature_engine pipeline
    X, y = build_dataset(df)

    if X.empty or len(X) < 50:
        raise ValueError(
            f"Insufficient features after build_dataset: {len(X)} rows. "
            f"Need at least 50 rows for time-series CV."
        )

    logger.info(f"Built feature matrix: X.shape={X.shape}, y.shape={y.shape}")
    logger.info(f"Positive class ratio: {y.mean():.4f}")

    return X, y


def parse_models(models_str: str) -> List[str]:
    """Parse comma-separated model list.

    Args:
        models_str: Comma-separated model names

    Returns:
        List of validated model names

    Raises:
        ValueError: If any model name is invalid
    """
    valid_models = {"lightgbm", "gru", "lstm"}
    models = [m.strip().lower() for m in models_str.split(",") if m.strip()]

    invalid = set(models) - valid_models
    if invalid:
        raise ValueError(
            f"Invalid model(s): {invalid}. Valid models are: {', '.join(sorted(valid_models))}"
        )

    return models if models else ["lightgbm", "gru"]


def determine_output_path(symbol: str, custom_path: str | None) -> Path:
    """Determine output file path.

    Args:
        symbol: Stock ticker symbol
        custom_path: Custom path if provided

    Returns:
        Path object for output file
    """
    if custom_path:
        return Path(custom_path)

    # Default path: data/reports/model_comparison_{symbol}.md
    base_dir = Path("data/reports")
    base_dir.mkdir(parents=True, exist_ok=True)

    return base_dir / f"model_comparison_{symbol.upper()}.md"


def main() -> int:
    """Main entry point for the compare_models script.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate dates
    try:
        start_date = validate_date(args.start)
        end_date = validate_date(args.end)
    except ValueError as e:
        logger.error(f"Date validation error: {e}")
        return 1

    if start_date >= end_date:
        logger.error(f"Start date must be before end date: {args.start} >= {args.end}")
        return 1

    # Validate and parse models
    try:
        model_list = parse_models(args.models)
    except ValueError as e:
        logger.error(f"Model validation error: {e}")
        return 1

    logger.info(f"Running model comparison for {args.symbol.upper()}")
    logger.info(f"Date range: {args.start} to {args.end}")
    logger.info(f"Models: {', '.join(model_list)}")

    # Step 1: Load features
    try:
        X, y = load_features(args.symbol.upper(), start_date, end_date)
    except ValueError as e:
        logger.error(f"Feature loading failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error during feature loading: {e}", exc_info=True)
        return 1

    # Step 2: Train all models
    try:
        logger.info("Training models...")
        results = train_all_models(
            X=X,
            y=y,
            symbol=None,  # X, y provided directly
            model_types=model_list,
            dl_config=DLConfig(),
        )
        logger.info(f"Trained {len(results)} models: {list(results.keys())}")
    except ValueError as e:
        logger.error(f"Model training failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error during model training: {e}", exc_info=True)
        return 1

    # Step 3: Generate comparison report
    try:
        logger.info("Generating comparison report...")
        date_range = (args.start, args.end)
        report = generate_comparison_report(
            results=results,
            symbol=args.symbol.upper(),
            date_range=date_range,
            X=X,
            dl_config=DLConfig(),
        )
        logger.info("Report generated successfully")
    except ValueError as e:
        logger.error(f"Report generation failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error during report generation: {e}", exc_info=True)
        return 1

    # Step 4: Format as Markdown
    try:
        logger.info("Formatting as Markdown...")
        markdown = format_comparison_markdown(report)
        logger.info(f"Markdown length: {len(markdown)} characters")
    except ValueError as e:
        logger.error(f"Markdown formatting failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error during markdown formatting: {e}", exc_info=True)
        return 1

    # Step 5: Write to file
    try:
        output_path = determine_output_path(args.symbol, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        logger.info(f"Report written to: {output_path}")
    except Exception as e:
        logger.error(f"Failed to write output file: {e}", exc_info=True)
        return 1

    # Print summary to stdout
    print("\n" + "=" * 60)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 60)
    print(f"Symbol: {args.symbol.upper()}")
    print(f"Date Range: {args.start} to {args.end}")
    print(f"Data Points: {report['metadata'].get('data_points', 'N/A')}")
    print("-" * 60)
    print("Predictions:")
    for model_name, pred in report["predictions"].items():
        if model_name == "fusion_score":
            print(f"  {model_name}: {pred:.4f}")
        else:
            signal = "UP" if pred > 0.5 else "DOWN"
            print(f"  {model_name}: {pred:.4f} ({signal})")
    print("-" * 60)
    print("Performance (AUC):")
    for model_name, metrics in report["metrics"].items():
        auc = metrics.get("mean_auc", "N/A")
        if isinstance(auc, float):
            print(f"  {model_name}: {auc:.4f}")
        else:
            print(f"  {model_name}: {auc}")
    print("=" * 60)
    print(f"\nFull report saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())