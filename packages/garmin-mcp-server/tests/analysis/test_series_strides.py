"""Strides read off the time series (#1494)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.series_strides import detect_series_strides

_JOG = (2.38, 178.0, 145.0)  # 7:00/km
_STRIDE = (5.0, 205.0, 160.0)  # 3:20/km
_RECOVERY = (2.2, 175.0, 158.0)


def _series(
    segments: list[tuple[int, tuple[float, float, float]]],
) -> list[dict[str, Any]]:
    """One sample per second: ``(seconds, (speed, cadence, hr))`` segments."""
    samples: list[dict[str, Any]] = []
    t = 0
    for seconds, (speed, cadence, hr) in segments:
        for _ in range(seconds):
            samples.append(
                {
                    "timestamp_s": float(t),
                    "speed": speed,
                    "cadence": cadence,
                    "heart_rate": hr,
                }
            )
            t += 1
    return samples


def _with_strides(reps: int, stride_s: int = 20) -> list[dict[str, Any]]:
    segments: list[tuple[int, tuple[float, float, float]]] = [(1200, _JOG)]
    for _ in range(reps):
        segments += [(stride_s, _STRIDE), (90, _RECOVERY)]
    segments.append((300, _JOG))
    return _series(segments)


@pytest.mark.unit
def test_detects_four_strides_from_series() -> None:
    samples = _with_strides(4)
    # A 3 s GPS speed dip in the 3rd stride, the cadence held.
    third = 1200 + 2 * 110 + 8
    for sample in samples[third : third + 3]:
        sample["speed"] = 1.6

    reps = detect_series_strides(samples)

    assert len(reps) == 4
    assert all(15 <= rep.duration_s <= 25 for rep in reps)
    assert reps[0].t_from_s == 1200
    assert reps[0].recovery_after_s == 90
    assert reps[-1].recovery_after_s is None
    assert reps[0].avg_pace_s_per_km == pytest.approx(200.0)
    assert reps[0].peak_cadence == 205.0


@pytest.mark.unit
def test_single_surge_is_not_strides() -> None:
    assert detect_series_strides(_with_strides(1)) == []


@pytest.mark.unit
def test_long_effort_over_45s_is_not_stride() -> None:
    assert detect_series_strides(_with_strides(4, stride_s=60)) == []
