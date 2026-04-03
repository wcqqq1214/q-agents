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
ASSET_TYPE_ALIASES: dict[str, AssetType] = {
    "stock": "stocks",
    "stocks": "stocks",
    "crypto": "crypto",
}


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


def normalize_asset_type(asset_type: str | None, asset: str | None) -> AssetType:
    """Normalize stored asset-type values to the API contract.

    Historical report files may contain mixed casing, trailing whitespace, or a
    singular `"stock"` value. Normalize those obvious legacy variants first,
    then fall back to symbol-based classification for anything unknown.

    Args:
        asset_type: Stored value from `report.json`, if present.
        asset: Associated symbol used for fallback classification.

    Returns:
        A contract-safe `"stocks"` or `"crypto"` value.
    """

    normalized = (asset_type or "").strip().lower()
    if normalized == "crypto":
        return "crypto"
    if normalized in {"stock", "stocks"}:
        return "stocks"
    return classify_asset_type(asset)


def normalize_asset_type(value: str | None, asset: str | None) -> AssetType:
    """Normalize stored asset-type values and fall back to symbol classification.

    Args:
        value: Asset type read from persisted report data.
        asset: Symbol used as a fallback when the stored value is missing or invalid.

    Returns:
        Canonical asset type accepted by the API contract.
    """

    normalized = (value or "").strip().lower()
    if normalized in ASSET_TYPE_ALIASES:
        return ASSET_TYPE_ALIASES[normalized]
    return classify_asset_type(asset)
