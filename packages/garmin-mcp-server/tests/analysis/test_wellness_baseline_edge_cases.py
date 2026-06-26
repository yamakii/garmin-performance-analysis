"""Boundary / edge-case unit tests for the personal wellness baseline (#562).

Complements ``test_wellness_baseline.py`` (#555 happy paths) by pinning down the
robustness corners the spike (#527) flagged: the *strict* +/-1 SD boundary, the
pre-2025 HRV/readiness data floor (window all-null), partial-metric coverage
(one metric present, another absent), and a zero-spread constant series (no
``ZeroDivisionError``, no ``inf``/``nan`` z).

Series are chosen so the *population* mean / SD come out exact:
``[48,52,56,60,64,68,72]`` -> mean=60, pstdev=8.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from garmin_mcp.analysis.wellness_baseline import (
    compute_metric_baseline,
    compute_wellness_baseline_deviation,
)

# mean=60, population SD=8
_HRV_SERIES = [48.0, 52.0, 56.0, 60.0, 64.0, 68.0, 72.0]


@pytest.mark.unit
def test_baseline_exactly_one_sd_boundary() -> None:
    """HRV mean=60 SD=8, today=52 -> z=-1.0 exactly; strict band keeps 'within'.

    ``flag='low'`` requires ``z < -sd_threshold`` (strict), so a value sitting
    *exactly* one SD below the mean is still inside the band, not adverse.
    """
    result = compute_metric_baseline(
        _HRV_SERIES, 52.0, direction="low_is_bad", sd_threshold=1.0
    )

    assert result.z == -1.0
    assert result.flag == "within"
    assert result.adverse is False
    assert result.n == 7


@pytest.mark.unit
def test_baseline_data_floor_pre_2025() -> None:
    """Window entirely null (HRV/readiness reported only from 2025-05) -> every
    metric 'insufficient', overall_flag False, no exception."""
    rows: list[dict[str, Any]] = [
        {
            "date": f"2025-04-{i + 1:02d}",
            "hrv_overnight_ms": None,
            "training_readiness": None,
            "resting_hr": None,
        }
        for i in range(30)
    ]
    rows.append(
        {
            "date": "2025-05-01",
            "hrv_overnight_ms": None,
            "training_readiness": None,
            "resting_hr": None,
        }
    )

    result = compute_wellness_baseline_deviation(rows)

    for key in ("hrv", "readiness", "rhr"):
        assert result[key]["flag"] == "insufficient"
        assert result[key]["mean"] is None
    assert result["overall_flag"] is False


@pytest.mark.unit
def test_baseline_partial_metrics() -> None:
    """HRV sufficient + readiness entirely null -> HRV computes (low/adverse),
    readiness 'insufficient', no exception."""
    rows: list[dict[str, Any]] = [
        {
            "date": f"2026-06-{i + 1:02d}",
            "hrv_overnight_ms": hrv,
            "training_readiness": None,
            "resting_hr": 50.0,
        }
        for i, hrv in enumerate(_HRV_SERIES)
    ]
    rows.append(
        {
            "date": "2026-06-08",
            "hrv_overnight_ms": 48.0,
            "training_readiness": None,
            "resting_hr": 50.0,
        }
    )

    result = compute_wellness_baseline_deviation(rows)

    assert result["hrv"]["flag"] == "low"
    assert result["hrv"]["mean"] == 60.0
    assert result["hrv"]["adverse"] is True
    assert result["readiness"]["flag"] == "insufficient"
    assert result["readiness"]["mean"] is None


@pytest.mark.unit
def test_baseline_zero_std_constant_series() -> None:
    """Constant 30-day series (SD=0), today far below -> graceful degeneration:
    no ZeroDivisionError, z finite (not inf/nan), not flagged adverse."""
    series = [60.0] * 30

    result = compute_metric_baseline(series, 48.0, direction="low_is_bad")

    assert result.flag in {"within", "insufficient"}
    assert result.adverse is False
    # z must not blow up via division by zero.
    assert result.z is None or (not math.isinf(result.z) and not math.isnan(result.z))
