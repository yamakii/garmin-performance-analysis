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
    masked_split_hr,
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
    """A surge that becomes the new pace: HR settles at 155 +-1 while speed
    holds at 2.8 m/s (from 2.4) -- the plateau start ends the recovery."""
    end = 200

    def hr(t: int) -> float:
        if t < 180:
            return BASELINE
        if t < end + 10:
            return 170.0
        return 154.0 if t % 2 else 156.0

    samples = _trace(400, hr, speed=lambda t: 2.4 if t < 180 else 2.8)

    assert recovery_end(samples, Event("burst", 180.0, float(end)), None) == end + 10


@pytest.mark.unit
def test_recovery_end_plateau_ignored_when_speed_drops() -> None:
    """After a stride HR sits at 157 +-1 for 30 s on a slower jog (1.9 m/s
    from 2.4) and is back at 146 by +70 s: that plateau is the recovery
    coming down, not a new level, so the recovery ends at +70 s (#1320)."""
    end = 200

    def hr(t: int) -> float:
        if t < 180:
            return BASELINE
        if t < end:
            return 165.0
        if t < end + 30:
            return 156.0 if t % 2 else 158.0
        if t < end + 70:
            # Coming down slowly: still above baseline + 3 at +69 s.
            return 157.0 - 0.175 * (t - end - 30)
        return 146.0

    def speed(t: int) -> float:
        if t < 180:
            return 2.4
        if t < end:
            return 4.8
        return 1.9 if t < end + 70 else 2.4

    samples = _trace(400, hr, speed=speed)

    assert recovery_end(samples, Event("burst", 180.0, float(end)), None) == end + 70


@pytest.mark.unit
def test_steady_mask_chained_strides_keep_first_baseline() -> None:
    """Two strides 35 s apart: the second starts while HR is still ~158 from
    the first. It recovers to the steady 145 before the first stride, not to
    that 158, so the mask runs from the first stride to HR's return at 230
    instead of stopping as soon as the second stride ends (#1320)."""

    def hr(t: int) -> float:
        if 100 <= t < 115 or 150 <= t < 165:
            return 165.0
        if 115 <= t < 150:
            return 157.0 if t % 2 else 159.0
        if 165 <= t < 230:
            # Coming down from 158 to 150, still above baseline + 3.
            return 158.0 - 0.125 * (t - 165)
        return BASELINE if t < 100 else 146.0

    def speed(t: int) -> float:
        if 100 <= t < 115 or 150 <= t < 165:
            return 4.8
        return 1.9 if 115 <= t < 230 else 2.4

    samples = _trace(400, hr, speed=speed)

    mask = steady_mask(samples, [])

    assert [t for t, keep in enumerate(mask) if not keep] == list(range(100, 230))


@pytest.mark.unit
def test_masked_split_hr_excludes_masked_samples() -> None:
    """A split whose steady seconds sit at 145 and whose masked seconds sit at
    162 reads 145 -- the masked stride never reaches the kilometre's HR."""
    samples = _trace(100, lambda t: 162.0 if 40 <= t < 70 else BASELINE)
    mask = [not 40 <= t < 70 for t in range(100)]
    splits = [{"split_index": 1, "start_s": 0.0, "end_s": 100.0, "avg_hr": 150.0}]

    (split,) = masked_split_hr(samples, mask, splits)

    assert split["avg_hr"] == BASELINE
    assert split["max_hr"] == BASELINE
    # The input is left as it was.
    assert splits[0]["avg_hr"] == 150.0


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
