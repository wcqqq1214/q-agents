from __future__ import annotations

from app.ml.signal_filter import apply_similarity_signal_filter


def test_similarity_signal_filter_confirms_direction():
    summary = apply_similarity_signal_filter(
        0.44,
        {
            "n_matches": 8,
            "avg_future_return_3d": -0.0229,
        },
    )

    assert summary["alignment"] == "confirmed"
    assert summary["position_multiplier"] == 1.25
    assert summary["adjusted_probability"] < 0.44


def test_similarity_signal_filter_contradicts_direction():
    summary = apply_similarity_signal_filter(
        0.56,
        {
            "n_matches": 8,
            "avg_future_return_3d": -0.0229,
        },
    )

    assert summary["alignment"] == "contradicted"
    assert summary["position_multiplier"] == 0.5
    assert 0.5 < summary["adjusted_probability"] < 0.56
