"""Steady-running windows for the HR ceiling (#1313).

Every trace here is one sample per second with a known shape, so the event
and recovery boundaries can be stated exactly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from garmin_mcp.analysis.hr_windows import (
    HR_RECOVERY_CAP_S,
    Event,
    judged_share,
    recovery_end,
    seconds_over,
    steady_mask,
)

BASELINE = 145.0


def _trace(
    seconds: int,
    hr: Callable[[int], float],
    speed: Callable[[int], float | None] | None = None,
) -> list[dict[str, Any]]:
    """``seconds`` samples at 1 Hz with ``hr(t)`` (and ``speed(t)``)."""
    return [
        {
            "timestamp_s": float(t),
            "heart_rate": hr(t),
            "speed": None if speed is None else speed(t),
        }
        for t in range(seconds)
    ]


@pytest.mark.unit
def test_steady_mask_excludes_stopped_samples() -> None:
    """Speed 0 for 10 s at t=100: exactly those ten samples are masked."""
    samples = _trace(
        300,
        lambda _t: BASELINE,
        speed=lambda t: 0.0 if 100 <= t < 110 else 2.8,
    )

    mask = steady_mask(samples, [])

    assert [t for t, keep in enumerate(mask) if not keep] == list(range(100, 110))


@pytest.mark.unit
def test_recovery_end_returns_to_baseline() -> None:
    """160 after a burst, back to 146 at +40 s and held -> end = +40 s."""
    end = 200

    def hr(t: int) -> float:
        if t < 180:
            return BASELINE
        if t < end:
            return 165.0
        if t < end + 40:
            return 160.0 - 0.275 * (t - end)
        return 146.0

    samples = _trace(400, hr)

    assert recovery_end(samples, Event("burst", 180.0, float(end)), None) == end + 40


@pytest.mark.unit
def test_recovery_end_plateau_new_level() -> None:
    """HR settles at 155 +-1 after a burst: the plateau start ends it."""
    end = 200

    def hr(t: int) -> float:
        if t < 180:
            return BASELINE
        if t < end + 10:
            return 170.0
        return 154.0 if t % 2 else 156.0

    samples = _trace(400, hr)

    assert recovery_end(samples, Event("burst", 180.0, float(end)), None) == end + 10


@pytest.mark.unit
def test_recovery_end_small_burst_is_short() -> None:
    """A 5 s pickup peaking at 147 needs no recovery window to speak of."""
    end = 205

    def hr(t: int) -> float:
        if 200 <= t < end:
            return 147.0
        return 146.0 if t >= end else BASELINE

    samples = _trace(400, hr)

    assert recovery_end(samples, Event("burst", 200.0, float(end)), None) <= end + 10


@pytest.mark.unit
def test_recovery_end_capped() -> None:
    """HR swinging +-6 bpm never settles: the recovery stops at the cap."""
    end = 200

    def hr(t: int) -> float:
        if t < end:
            return BASELINE
        return 149.0 if t % 2 else 161.0

    samples = _trace(600, hr)

    assert (
        recovery_end(samples, Event("burst", 180.0, float(end)), None)
        == end + HR_RECOVERY_CAP_S
    )


@pytest.mark.unit
def test_recovery_end_pause_resume() -> None:
    """130 at resume, 144 from resume + 60 s -> end = resume + 60 s."""
    resume = 300

    def hr(t: int) -> float:
        if t < resume:
            return BASELINE
        if t < resume + 60:
            return 130.0 + (t - resume) % 10
        return 144.0

    samples = _trace(600, hr)

    event = Event("pause_resume", float(resume - 1), float(resume))
    assert recovery_end(samples, event, None) == resume + 60


@pytest.mark.unit
def test_steady_mask_excludes_event_and_recovery() -> None:
    """A stride lap ending at 500, HR recovered at 560: 500-559 masked."""

    def hr(t: int) -> float:
        if t < 480:
            return BASELINE
        if t < 500:
            return 160.0
        if t < 560:
            return 150.0 + t % 10
        return BASELINE

    samples = _trace(900, hr)
    splits = [
        {"role_phase": "run", "start_s": 0.0, "end_s": 480.0},
        {"role_phase": "stride", "start_s": 480.0, "end_s": 500.0},
        {"role_phase": "run", "start_s": 500.0, "end_s": 900.0},
    ]

    mask = steady_mask(samples, splits)

    assert not any(mask[500:560])
    assert all(mask[560:])
    assert all(mask[:480])


@pytest.mark.unit
def test_seconds_over_ignores_masked() -> None:
    """HR 160 only where the mask drops it: nothing over a 150 ceiling."""
    samples = _trace(300, lambda t: 160.0 if 100 <= t < 160 else BASELINE)
    mask = [not 100 <= t < 160 for t in range(300)]

    over = seconds_over(samples, mask, 150)

    assert over is not None
    assert over["seconds_over"] == 0
    assert over["pct_over"] == 0
    assert judged_share(samples, mask) == pytest.approx(0.8)
