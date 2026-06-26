"""Tests for the quarterly threshold-anchored Critical Speed fit."""

import pytest

from garmin_mcp.objective_fitness.critical_speed import (
    CriticalSpeedFit,
    fit_critical_speed,
    quarterly_critical_speed,
)

# Points on the line d = 2.83 * t + 234 (Epic #526 spike confirmed values).
_PERFECT_LINE = [
    (120.0, 573.6),
    (600.0, 1932.0),
    (1500.0, 4479.0),
    (2700.0, 7875.0),
]


@pytest.mark.unit
class TestFitCriticalSpeed:
    def test_fit_critical_speed_r2_perfect(self):
        fit = fit_critical_speed(_PERFECT_LINE)
        assert fit is not None
        assert isinstance(fit, CriticalSpeedFit)
        assert abs(fit.cs_mps - 2.83) < 0.01
        assert fit.r_squared > 0.999
        assert fit.n_points == 4

    def test_fit_critical_speed_cs_pace(self):
        fit = fit_critical_speed(_PERFECT_LINE)
        assert fit is not None
        # 1000 / 2.83 = 353.36 sec/km ~= 5:53/km.
        assert abs(fit.cs_pace_sec_per_km - 353.4) < 1.0

    def test_fit_critical_speed_label_threshold_anchored(self):
        fit = fit_critical_speed(_PERFECT_LINE)
        assert fit is not None
        assert "threshold-anchored" in fit.label
        # The label must not claim all-duration / anaerobic validity.
        assert "anaerobic" not in fit.label.lower()
        assert "all-duration" not in fit.label.lower()

    def test_fit_critical_speed_insufficient_points(self):
        assert fit_critical_speed([(600.0, 1932.0)]) is None


@pytest.mark.unit
class TestQuarterlyCriticalSpeed:
    def test_quarterly_critical_speed_buckets_by_quarter(self):
        # Q1 efforts (Jan/Feb) and Q2 efforts (Apr/May), each with >=2 points.
        efforts = [
            ("2026-01-10", 120.0, 573.6),
            ("2026-01-10", 600.0, 1932.0),
            ("2026-02-15", 1500.0, 4479.0),
            ("2026-04-05", 120.0, 560.0),
            ("2026-04-05", 600.0, 1900.0),
            ("2026-05-20", 1500.0, 4400.0),
        ]
        result = quarterly_critical_speed(efforts)
        assert len(result) == 2
        quarters = {row["quarter"] for row in result}
        assert quarters == {"2026-Q1", "2026-Q2"}
        for row in result:
            # YYYY-Qn format.
            assert row["quarter"][:4].isdigit()
            assert row["quarter"][4:6] == "-Q"
            assert row["quarter"][6].isdigit()
            assert row["cs_mps"] > 0
            assert "threshold-anchored" in row["label"]

    def test_quarterly_critical_speed_no_dprime_surfaced(self):
        efforts = [
            ("2026-04-05", 120.0, 573.6),
            ("2026-04-05", 600.0, 1932.0),
            ("2026-05-20", 1500.0, 4479.0),
        ]
        result = quarterly_critical_speed(efforts)
        assert result
        for row in result:
            assert "d_prime" not in row
            assert "d_prime_m" not in row
