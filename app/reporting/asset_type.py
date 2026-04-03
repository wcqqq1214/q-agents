"""Shared helper for classifying whether a symbol is a stock or crypto.

This module is intentionally small and dependency-free so it can be reused by
graph orchestration and report writing code without creating import cycles.
"""

from __future__ import annotations

import re
from typing import Literal

AssetType = Literal["stocks", "crypto"]

# Single source of truth: keep this list in sync wherever symbol routing depends on it.
CRYPTO_TICKERS: frozenset[str] = frozenset(
    {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK"}
)


def classify_asset_type(asset: str | None) -> AssetType:
    """Classify an asset symbol as crypto or stocks.

    Args:
        asset: User-provided or extracted symbol. Accepts plain tickers ("BTC")
            and common Yahoo Finance crypto pairs ("BTC-USD").

    Returns:
        "crypto" for known crypto symbols/pairs, otherwise "stocks".
    """

    normalized = (asset or "").strip().upper()
    pair = re.search(r"\b([A-Z]{2,10})-USD\b", normalized)
    if pair:
        base = pair.group(1)
        return "crypto" if base in CRYPTO_TICKERS else "stocks"
    if normalized in CRYPTO_TICKERS:
        return "crypto"
    return "stocks"
