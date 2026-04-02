from __future__ import annotations

import math
from typing import Any, Literal, TypedDict

SignalDirection = Literal["bullish", "bearish", "neutral"]
SignalAlignment = Literal["confirmed", "contradicted", "neutral", "unavailable"]

CONFIRMED_POSITION_MULTIPLIER = 1.25
CONTRADICTED_POSITION_MULTIPLIER = 0.5
NEUTRAL_POSITION_MULTIPLIER = 1.0


class SignalFilterSummary(TypedDict):
    """Compact summary of the similarity-aware signal adjustment."""

    raw_probability: float
    adjusted_probability: float
    model_direction: SignalDirection
    similarity_direction: SignalDirection
    alignment: SignalAlignment
    position_multiplier: float
    similarity_avg_return_3d: float | None
    historical_matches: int


def direction_from_probability(probability: float) -> SignalDirection:
    """Map a probability to a directional label around the 0.5 boundary."""

    if probability > 0.5:
        return "bullish"
    if probability < 0.5:
        return "bearish"
    return "neutral"


def direction_from_avg_return(avg_return: float | None) -> SignalDirection:
    """Map an average forward return to a directional label."""

    if avg_return is None or not math.isfinite(avg_return):
        return "neutral"
    if avg_return > 0:
        return "bullish"
    if avg_return < 0:
        return "bearish"
    return "neutral"


def apply_similarity_signal_filter(
    probability: Any,
    historical_similarity: dict[str, Any] | None,
) -> SignalFilterSummary:
    """Adjust a raw model probability using historical-similarity direction."""

    raw_probability = (
        float(probability)
        if isinstance(probability, (int, float)) and math.isfinite(float(probability))
        else float("nan")
    )
    if not math.isfinite(raw_probability):
        return {
            "raw_probability": float("nan"),
            "adjusted_probability": float("nan"),
            "model_direction": "neutral",
            "similarity_direction": "neutral",
            "alignment": "unavailable",
            "position_multiplier": NEUTRAL_POSITION_MULTIPLIER,
            "similarity_avg_return_3d": None,
            "historical_matches": 0,
        }

    model_direction = direction_from_probability(raw_probability)
    historical_matches = int(historical_similarity.get("n_matches", 0)) if historical_similarity else 0

    similarity_avg_return_3d: float | None = None
    if historical_similarity:
        raw_avg = historical_similarity.get("avg_future_return_3d")
        if isinstance(raw_avg, (int, float)) and math.isfinite(float(raw_avg)):
            similarity_avg_return_3d = float(raw_avg)

    similarity_direction = (
        direction_from_avg_return(similarity_avg_return_3d)
        if historical_matches > 0
        else "neutral"
    )

    if historical_matches <= 0:
        alignment: SignalAlignment = "unavailable"
        position_multiplier = NEUTRAL_POSITION_MULTIPLIER
    elif model_direction == "neutral" or similarity_direction == "neutral":
        alignment = "neutral"
        position_multiplier = NEUTRAL_POSITION_MULTIPLIER
    elif similarity_direction == model_direction:
        alignment = "confirmed"
        position_multiplier = CONFIRMED_POSITION_MULTIPLIER
    else:
        alignment = "contradicted"
        position_multiplier = CONTRADICTED_POSITION_MULTIPLIER

    adjusted_probability = min(
        max(0.5 + (raw_probability - 0.5) * position_multiplier, 0.0),
        1.0,
    )

    return {
        "raw_probability": raw_probability,
        "adjusted_probability": adjusted_probability,
        "model_direction": model_direction,
        "similarity_direction": similarity_direction,
        "alignment": alignment,
        "position_multiplier": position_multiplier,
        "similarity_avg_return_3d": similarity_avg_return_3d,
        "historical_matches": historical_matches,
    }
