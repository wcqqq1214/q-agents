"""Technical-section adapters for the daily digest pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.digest.models import TechnicalSection
from app.quant.generate_report import generate_report as generate_quant_report
from app.tools.finance_tools import get_stock_data

logger = logging.getLogger(__name__)

_KNOWN_CRYPTO_TICKERS = {
    "BTC",
    "ETH",
    "SOL",
    "DOGE",
    "XRP",
    "ADA",
    "BNB",
    "AVAX",
    "LINK",
    "LTC",
}


def classify_asset_type(ticker: str) -> str:
    """Classify digest symbols into equity or crypto buckets.

    Args:
        ticker: Configured ticker symbol from the digest universe.

    Returns:
        str: ``"crypto"`` for Yahoo-compatible crypto symbols, otherwise
        ``"equity"``.
    """

    normalized = (ticker or "").strip().upper()
    if normalized in _KNOWN_CRYPTO_TICKERS or normalized.endswith("-USD"):
        return "crypto"
    return "equity"


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _trend_from_indicators(indicators: dict[str, Any]) -> str:
    last_close = _safe_float(indicators.get("last_close"))
    sma_20 = _safe_float(indicators.get("sma_20"))
    macd_line = _safe_float(indicators.get("macd_line"))
    macd_signal = _safe_float(indicators.get("macd_signal"))
    if (
        last_close is not None
        and sma_20 is not None
        and macd_line is not None
        and macd_signal is not None
        and last_close >= sma_20
        and macd_line >= macd_signal
    ):
        return "bullish"
    if (
        last_close is not None
        and sma_20 is not None
        and macd_line is not None
        and macd_signal is not None
        and last_close < sma_20
        and macd_line < macd_signal
    ):
        return "bearish"
    return "neutral"


def _levels_from_indicators(indicators: dict[str, Any]) -> dict[str, float | None]:
    support = _safe_float(indicators.get("bb_lower")) or _safe_float(indicators.get("sma_20"))
    resistance = _safe_float(indicators.get("bb_upper")) or _safe_float(indicators.get("sma_20"))
    return {"support": support, "resistance": resistance}


def _filtered_indicator_snapshot(indicators: dict[str, Any]) -> dict[str, float | None]:
    return {
        "last_close": _safe_float(indicators.get("last_close")),
        "sma_20": _safe_float(indicators.get("sma_20")),
        "macd_line": _safe_float(indicators.get("macd_line")),
        "macd_signal": _safe_float(indicators.get("macd_signal")),
        "macd_histogram": _safe_float(indicators.get("macd_histogram")),
        "price_change_pct": _safe_float(indicators.get("price_change_pct")),
    }


def _technical_error_section(ticker: str, asset_type: str, exc: Exception) -> TechnicalSection:
    return {
        "ticker": ticker,
        "asset_type": "crypto" if asset_type == "crypto" else "equity",
        "status": "error",
        "summary": "Technical snapshot unavailable for this run.",
        "trend": "neutral",
        "levels": {"support": None, "resistance": None},
        "indicators": {
            "last_close": None,
            "sma_20": None,
            "macd_line": None,
            "macd_signal": None,
            "macd_histogram": None,
            "price_change_pct": None,
        },
        "ml_signal": None,
        "error": f"{type(exc).__name__}: {exc}",
    }


def _section_from_quant_report(ticker: str, report: dict[str, Any]) -> TechnicalSection:
    indicators = report.get("indicators", {}) if isinstance(report.get("indicators"), dict) else {}
    levels = report.get("levels", {}) if isinstance(report.get("levels"), dict) else {}
    ml_quant = report.get("ml_quant", {}) if isinstance(report.get("ml_quant"), dict) else {}
    ml_signal = (
        {
            "model": ml_quant.get("model"),
            "prediction": ml_quant.get("prediction"),
            "prob_up": ml_quant.get("prob_up"),
            "final_prediction": ml_quant.get("final_prediction"),
            "final_prob_up": ml_quant.get("final_prob_up"),
        }
        if ml_quant
        else None
    )
    return {
        "ticker": ticker,
        "asset_type": "equity",
        "status": "ok",
        "summary": str(report.get("summary") or f"{ticker} technical view unavailable."),
        "trend": str(report.get("trend") or _trend_from_indicators(indicators)),
        "levels": {
            "support": _safe_float(levels.get("support")),
            "resistance": _safe_float(levels.get("resistance")),
        },
        "indicators": _filtered_indicator_snapshot(indicators),
        "ml_signal": ml_signal,
        "error": None,
    }


def _section_from_crypto_data(ticker: str, data: dict[str, Any]) -> TechnicalSection:
    if data.get("error"):
        raise ValueError(str(data["error"]))

    trend = _trend_from_indicators(data)
    indicators = _filtered_indicator_snapshot(data)
    levels = _levels_from_indicators(data)
    last_close = indicators["last_close"]
    sma_20 = indicators["sma_20"]
    price_relation = "near"
    if last_close is not None and sma_20 is not None:
        if last_close > sma_20:
            price_relation = "above"
        elif last_close < sma_20:
            price_relation = "below"

    macd_line = indicators["macd_line"]
    macd_signal = indicators["macd_signal"]
    macd_bias = "mixed"
    if macd_line is not None and macd_signal is not None:
        macd_bias = "positive MACD" if macd_line >= macd_signal else "negative MACD"

    return {
        "ticker": ticker,
        "asset_type": "crypto",
        "status": "ok",
        "summary": f"{ticker} technical view is {trend}; price {price_relation} SMA20 with {macd_bias}.",
        "trend": trend,
        "levels": levels,
        "indicators": indicators,
        "ml_signal": None,
        "error": None,
    }


async def build_technical_section(ticker: str, run_dir: Path) -> TechnicalSection:
    """Build one digest technical section for an equity or crypto ticker.

    Args:
        ticker: Configured digest symbol such as ``"AAPL"`` or ``"BTC"``.
        run_dir: Digest run directory where sub-artifacts may be written.

    Returns:
        TechnicalSection: Compact digest snapshot with trend, indicators, and
        graceful error metadata when the upstream adapter fails.
    """

    normalized = (ticker or "").strip().upper()
    asset_type = classify_asset_type(normalized)

    try:
        if asset_type == "equity":
            report = await asyncio.to_thread(
                generate_quant_report, normalized, str(run_dir / normalized)
            )
            return _section_from_quant_report(normalized, report)

        raw = await asyncio.to_thread(
            get_stock_data.invoke,
            {"ticker": f"{normalized}-USD", "period": "3mo"},
        )
        data = raw if isinstance(raw, dict) else json.loads(str(raw))
        return _section_from_crypto_data(normalized, data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build technical section for %s: %s", normalized, exc)
        return _technical_error_section(normalized, asset_type, exc)
