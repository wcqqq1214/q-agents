from __future__ import annotations

import math
from typing import Any, Literal, TypedDict

SignalDirection = Literal["bullish", "bearish", "neutral"]
SignalAlignment = Literal["confirmed", "contradicted", "neutral", "unavailable"]
MLSignalPolicy = Literal["primary_signal", "auxiliary_only", "event_driven_only"]

CONFIRMED_POSITION_MULTIPLIER = 1.25
CONTRADICTED_POSITION_MULTIPLIER = 0.5
NEUTRAL_POSITION_MULTIPLIER = 1.0
PRIMARY_SIGNAL_MIN_AUC = 0.55
AUXILIARY_SIGNAL_MIN_AUC = 0.53
PRIMARY_SIGNAL_AUC_MULTIPLIER = 1.0
AUXILIARY_SIGNAL_AUC_MULTIPLIER = 0.5
EVENT_DRIVEN_AUC_MULTIPLIER = 0.0


class SignalFilterSummary(TypedDict):
    """Compact summary of the similarity-aware signal adjustment."""

    raw_probability: float
    adjusted_probability: float
    model_direction: SignalDirection
    similarity_direction: SignalDirection
    alignment: SignalAlignment
    position_multiplier: float
    similarity_multiplier: float
    auc_multiplier: float
    ml_policy: MLSignalPolicy
    ml_signal_enabled: bool
    requested_symbol_auc: float | None
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


def _coerce_finite_float(value: Any) -> float | None:
    """Return a finite float or ``None`` when conversion is not possible."""

    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def determine_ml_policy(
    requested_symbol_auc: Any,
    *,
    requested_symbol_auc_unavailable: bool = False,
) -> MLSignalPolicy:
    """Map a single-symbol OOS AUC to the ML signal authority level."""

    auc_value = _coerce_finite_float(requested_symbol_auc)
    if auc_value is None:
        return "auxiliary_only" if requested_symbol_auc_unavailable else "primary_signal"
    if auc_value < AUXILIARY_SIGNAL_MIN_AUC:
        return "event_driven_only"
    if auc_value < PRIMARY_SIGNAL_MIN_AUC:
        return "auxiliary_only"
    return "primary_signal"


def auc_multiplier_from_policy(policy: MLSignalPolicy) -> float:
    """Return the risk multiplier implied by the ML authority policy."""

    if policy == "primary_signal":
        return PRIMARY_SIGNAL_AUC_MULTIPLIER
    if policy == "auxiliary_only":
        return AUXILIARY_SIGNAL_AUC_MULTIPLIER
    return EVENT_DRIVEN_AUC_MULTIPLIER


def apply_similarity_signal_filter(
    probability: Any,
    historical_similarity: dict[str, Any] | None,
    *,
    requested_symbol_auc: Any = None,
    requested_symbol_auc_unavailable: bool = False,
) -> SignalFilterSummary:
    """Adjust a raw model probability using similarity and single-symbol OOS AUC."""

    raw_probability = (
        float(probability)
        if isinstance(probability, (int, float)) and math.isfinite(float(probability))
        else float("nan")
    )
    auc_value = _coerce_finite_float(requested_symbol_auc)
    ml_policy = determine_ml_policy(
        requested_symbol_auc,
        requested_symbol_auc_unavailable=requested_symbol_auc_unavailable,
    )
    auc_multiplier = auc_multiplier_from_policy(ml_policy)
    if not math.isfinite(raw_probability):
        return {
            "raw_probability": float("nan"),
            "adjusted_probability": float("nan"),
            "model_direction": "neutral",
            "similarity_direction": "neutral",
            "alignment": "unavailable",
            "position_multiplier": NEUTRAL_POSITION_MULTIPLIER * auc_multiplier,
            "similarity_multiplier": NEUTRAL_POSITION_MULTIPLIER,
            "auc_multiplier": auc_multiplier,
            "ml_policy": ml_policy,
            "ml_signal_enabled": ml_policy != "event_driven_only",
            "requested_symbol_auc": auc_value,
            "similarity_avg_return_3d": None,
            "historical_matches": 0,
        }

    model_direction = direction_from_probability(raw_probability)
    historical_matches = (
        int(historical_similarity.get("n_matches", 0)) if historical_similarity else 0
    )

    similarity_avg_return_3d: float | None = None
    if historical_similarity:
        raw_avg = historical_similarity.get("avg_future_return_3d")
        if isinstance(raw_avg, (int, float)) and math.isfinite(float(raw_avg)):
            similarity_avg_return_3d = float(raw_avg)

    similarity_direction = (
        direction_from_avg_return(similarity_avg_return_3d) if historical_matches > 0 else "neutral"
    )

    if historical_matches <= 0:
        alignment: SignalAlignment = "unavailable"
        similarity_multiplier = NEUTRAL_POSITION_MULTIPLIER
    elif model_direction == "neutral" or similarity_direction == "neutral":
        alignment = "neutral"
        similarity_multiplier = NEUTRAL_POSITION_MULTIPLIER
    elif similarity_direction == model_direction:
        alignment = "confirmed"
        similarity_multiplier = CONFIRMED_POSITION_MULTIPLIER
    else:
        alignment = "contradicted"
        similarity_multiplier = CONTRADICTED_POSITION_MULTIPLIER

    position_multiplier = similarity_multiplier * auc_multiplier

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
        "similarity_multiplier": similarity_multiplier,
        "auc_multiplier": auc_multiplier,
        "ml_policy": ml_policy,
        "ml_signal_enabled": ml_policy != "event_driven_only",
        "requested_symbol_auc": auc_value,
        "similarity_avg_return_3d": similarity_avg_return_3d,
        "historical_matches": historical_matches,
    }
