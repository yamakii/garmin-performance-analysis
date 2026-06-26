"""Unit tests for personal wellness baseline helpers (#555).

Pure functions only -- no I/O. Cover the per-metric z-score band position
(low / within / high / insufficient, with adverse-direction wiring) and the
combined deviation that raises overall_flag when any metric deviates adversely.

Series are chosen so the *population* mean / SD come out exact:
``[48,52,56,60,64,68,72]`` -> mean=60, pstdev=8; ``[48,48,48,48,52,52,52,52]``
-> mean=50, pstdev=2.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.wellness_baseline import (
    compute_metric_baseline,
    compute_wellness_baseline_deviation,
)

# mean=60, population SD=8
_HRV_SERIES = [48.0, 52.0, 56.0, 60.0, 64.0, 68.0, 72.0]
# mean=50, population SD=2
_RHR_SERIES = [48.0, 48.0, 48.0, 48.0, 52.0, 52.0, 52.0, 52.0]


@pytest.mark.unit
def test_compute_metric_baseline_below_band() -> None:
    """HRV mean=60 SD=8, today=48 -> z=-1.5, flag='low', adverse=True."""
    result = compute_metric_baseline(_HRV_SERIES, 48.0, direction="low_is_bad")

    assert result.metric == "hrv"
    assert result.mean == 60.0
    assert result.std == 8.0
    assert result.z == -1.5
    assert result.flag == "low"
    assert result.adverse is True
    assert result.n == 7


@pytest.mark.unit
def test_compute_metric_baseline_within_band() -> None:
    """HRV mean=60 SD=8, today=58 -> z=-0.25, flag='within', adverse=False."""
    result = compute_metric_baseline(_HRV_SERIES, 58.0, direction="low_is_bad")

    assert result.z == -0.25
    assert result.flag == "within"
    assert result.adverse is False
    assert result.n == 7


@pytest.mark.unit
def test_compute_metric_baseline_rhr_elevated() -> None:
    """RHR (high_is_bad) mean=50 SD=2, today=55 -> z=+2.5, flag='high', adverse."""
    result = compute_metric_baseline(_RHR_SERIES, 55.0, direction="high_is_bad")

    assert result.metric == "rhr"
    assert result.mean == 50.0
    assert result.std == 2.0
    assert result.z == 2.5
    assert result.flag == "high"
    assert result.adverse is True
    assert result.n == 8


@pytest.mark.unit
def test_compute_metric_baseline_insufficient_samples() -> None:
    """Only 4 non-null samples (min_samples=7) -> 'insufficient', mean None, n=4."""
    series = [55.0, None, 60.0, None, 58.0, 62.0]  # 4 non-null
    result = compute_metric_baseline(
        series, 50.0, direction="low_is_bad", min_samples=7
    )

    assert result.flag == "insufficient"
    assert result.mean is None
    assert result.std is None
    assert result.z is None
    assert result.adverse is False
    assert result.n == 4


def _rows(
    *,
    hrv_today: float,
    readiness_today: float,
    rhr_today: float,
) -> list[dict[str, Any]]:
    """7 history rows + 1 today row.

    History bands: HRV mean=60/SD=8, readiness flat 70 (degenerate band -> all
    'within'), RHR flat 50 ('within'). Caller sets each today value.
    """
    rows: list[dict[str, Any]] = []
    for i, hrv in enumerate(_HRV_SERIES):
        rows.append(
            {
                "date": f"2026-06-{i + 1:02d}",
                "hrv_overnight_ms": hrv,
                "training_readiness": 70.0,
                "resting_hr": 50.0,
            }
        )
    rows.append(
        {
            "date": "2026-06-08",
            "hrv_overnight_ms": hrv_today,
            "training_readiness": readiness_today,
            "resting_hr": rhr_today,
        }
    )
    return rows


@pytest.mark.unit
def test_compute_deviation_overall_flag_true() -> None:
    """HRV today=48 (band mean60 SD8 -> low/adverse), others within -> True."""
    rows = _rows(hrv_today=48.0, readiness_today=70.0, rhr_today=50.0)

    result = compute_wellness_baseline_deviation(rows)

    assert result["date"] == "2026-06-08"
    assert result["hrv"]["flag"] == "low"
    assert result["hrv"]["adverse"] is True
    assert result["readiness"]["flag"] == "within"
    assert result["rhr"]["flag"] == "within"
    assert result["overall_flag"] is True


@pytest.mark.unit
def test_compute_deviation_overall_flag_false() -> None:
    """All metrics today inside their band -> overall_flag False."""
    rows = _rows(hrv_today=60.0, readiness_today=70.0, rhr_today=50.0)

    result = compute_wellness_baseline_deviation(rows)

    assert result["hrv"]["flag"] == "within"
    assert result["hrv"]["adverse"] is False
    assert result["readiness"]["flag"] == "within"
    assert result["rhr"]["flag"] == "within"
    assert result["overall_flag"] is False
