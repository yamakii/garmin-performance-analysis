"""The HR ceiling is a guard, judged on the time spent above it (Issue #1357).

The average let an early overshoot hide behind a slower finish: 2026-09-13
spent 30:22 (14.9%) of its steady running above 150 bpm, averaged 146 and read
on plan. Off plan now takes more than 5% of the judged time AND at least five
minutes above the ceiling; an average more than 10 bpm over stays 🔴.
"""

import pytest

from garmin_mcp.analysis.derivations import (
    compute_prescription_verdict,
    judge_hr_ceiling,
)
from garmin_mcp.analysis.plan_axes import AxisResult

LONG = {
    "session_type": "long",
    "title": "ロング 25km",
    "target_km": 25.0,
    "hr_high": 150,
}

# 25 km at an easy class: intensity and volume on plan, so the ceiling alone
# decides the verdict.
ACTUAL_AVG_146 = {
    "distance_km": 25.1,
    "duration_min": 200.0,
    "avg_hr": 146,
    "training_type": "aerobic_base",
}


@pytest.mark.unit
def test_verdict_hr_ceiling_off_by_time_over() -> None:
    """Half an hour above the ceiling is off plan whatever the average says."""
    result = compute_prescription_verdict(
        LONG,
        ACTUAL_AVG_146,
        ceiling_over={"seconds_over": 1822.0, "pct_over": 14.9},
    )

    assert result is not None
    assert result["verdict"] == "🟡"
    assert "hr_ceiling" not in result["on_plan"]
    assert any("30:22（14.9%）" in reason for reason in result["reasons"])


@pytest.mark.unit
def test_verdict_hr_ceiling_short_excursion_on_plan() -> None:
    """A few minutes over on a short run is a high share but not a miss."""
    easy = {"session_type": "easy", "title": "Z2ジョグ 30分", "hr_high": 150}
    actual = {"duration_min": 32.0, "avg_hr": 146, "training_type": "aerobic_base"}

    result = compute_prescription_verdict(
        easy, actual, ceiling_over={"seconds_over": 276.0, "pct_over": 14.4}
    )

    assert result is not None
    assert "hr_ceiling" in result["on_plan"]
    assert result["verdict"] == "✅"


@pytest.mark.unit
def test_verdict_hr_ceiling_falls_back_to_average() -> None:
    """Without a time series the average still decides, as before."""
    actual = {**ACTUAL_AVG_146, "avg_hr": 155}

    result = compute_prescription_verdict(LONG, actual, ceiling_over=None)

    assert result is not None
    assert result["verdict"] == "🟡"
    assert "hr_ceiling" not in result["on_plan"]
    assert any("平均HR 155bpm" in reason for reason in result["reasons"])


@pytest.mark.unit
def test_verdict_hr_ceiling_red_on_average_kept() -> None:
    """An average far over the ceiling is risk-side, time series or not."""
    actual = {**ACTUAL_AVG_146, "avg_hr": 162}

    result = compute_prescription_verdict(
        LONG, actual, ceiling_over={"seconds_over": 9000.0, "pct_over": 80.0}
    )

    assert result is not None
    assert result["verdict"] == "🔴"
    assert "hr_ceiling" not in result["on_plan"]


# --- verdict from judged axes (#1406) -------------------------------------------


def _axis(axis: str, status: str, severity: int) -> AxisResult:
    return AxisResult(axis, axis, "-", "-", status, severity, ())  # type: ignore[arg-type]


@pytest.mark.unit
def test_verdict_from_axes_is_worst_axis() -> None:
    """With axes, the verdict is the worst row; insufficient rows count for nothing."""
    axes = [
        _axis("stages", "on_plan", 0),
        _axis("hr_band", "insufficient", 0),
        _axis("strides", "short", 1),
    ]

    result = compute_prescription_verdict(LONG, ACTUAL_AVG_146, axes=axes)

    assert result is not None
    assert result["verdict"] == "🟡"
    assert result["on_plan"] == ["intensity_class", "volume", "stages"]
    assert result["axis_severity"] == {
        "intensity_class": 0,
        "volume": 0,
        "stages": 0,
        "hr_band": 0,
        "strides": 1,
    }
    # The ceiling is not judged here: it is one of the axes, or absent.
    assert "hr_ceiling" not in result["axis_severity"]


@pytest.mark.unit
def test_verdict_from_axes_all_on_plan() -> None:
    result = compute_prescription_verdict(
        LONG, ACTUAL_AVG_146, axes=[_axis("hr_ceiling", "on_plan", 0)]
    )

    assert result is not None
    assert result["verdict"] == "✅"
    assert "hr_ceiling" in result["on_plan"]


@pytest.mark.unit
def test_judge_hr_ceiling_matches_verdict_rule() -> None:
    """The shared ceiling rule: time over decides, 10 bpm over the average is 🔴."""
    assert judge_hr_ceiling(150, 146, {"seconds_over": 60, "pct_over": 1.0}) == (
        True,
        0,
        None,
    )
    kept, severity, reason = judge_hr_ceiling(
        150, 146, {"seconds_over": 1822.0, "pct_over": 14.9}
    )
    assert (kept, severity) == (False, 1)
    assert reason is not None
    assert judge_hr_ceiling(150, 161, None)[:2] == (False, 2)
    assert judge_hr_ceiling(150, None, None) == (None, 0, None)
