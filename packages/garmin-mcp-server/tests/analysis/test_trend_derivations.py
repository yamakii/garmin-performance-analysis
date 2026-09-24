"""Unit tests for the trend derivations (Issue #790).

Pure functions (no I/O): period delta %, consecutive build streak, cross-signal
fusion flags, and the trend headline-metrics fold.
"""

import pytest

from garmin_mcp.analysis.derivations import (
    compute_fusion_flags,
    compute_period_delta_pct,
    compute_trend_headline_metrics,
    count_consecutive_build_weeks,
    weeks_since_last_cutback,
)


@pytest.mark.unit
class TestWeeksSinceLastCutback:
    def test_weeks_since_last_cutback_latest_week(self) -> None:
        assert weeks_since_last_cutback([40, 42, 28]) == 1

    def test_weeks_since_last_cutback_older_week(self) -> None:
        assert weeks_since_last_cutback([40, 26, 30, 35]) == 3

    def test_weeks_since_last_cutback_none_without_drop(self) -> None:
        assert weeks_since_last_cutback([30, 32, 35]) is None
        assert weeks_since_last_cutback([]) is None

    def test_weeks_since_last_cutback_threshold_is_20_pct(self) -> None:
        # 40 -> 32.4 is a 19% drop (not a cutback); 40 -> 32 is exactly 20%.
        assert weeks_since_last_cutback([40, 32.4]) is None
        assert weeks_since_last_cutback([40, 32]) == 1

    def test_weeks_since_last_cutback_no_run_week(self) -> None:
        assert weeks_since_last_cutback([35, 0, 20]) == 2


@pytest.mark.unit
class TestComputePeriodDeltaPct:
    def test_delta_pct_positive(self) -> None:
        assert compute_period_delta_pct(110, 100) == 10.0

    def test_delta_pct_none_when_prior_zero(self) -> None:
        assert compute_period_delta_pct(5, 0) is None

    def test_delta_pct_none_when_operand_missing(self) -> None:
        assert compute_period_delta_pct(None, 100) is None


@pytest.mark.unit
class TestCountConsecutiveBuildWeeks:
    def test_consecutive_build_all_increasing(self) -> None:
        assert count_consecutive_build_weeks([30, 32, 35, 40]) == 4

    def test_consecutive_build_stops_at_decrease(self) -> None:
        assert count_consecutive_build_weeks([40, 32, 35, 38]) == 3

    def test_consecutive_build_flat_or_empty(self) -> None:
        assert count_consecutive_build_weeks([50, 40, 30]) == 1
        assert count_consecutive_build_weeks([]) == 0


@pytest.mark.unit
class TestComputeFusionFlags:
    def test_fusion_high_load_low_recovery_true(self) -> None:
        flags = compute_fusion_flags(
            acwr_status="high_risk", hrv_state="under_recovery", form_delta_pct=None
        )
        assert flags["high_load_low_recovery"] is True

    def test_fusion_all_false_when_signals_ok(self) -> None:
        flags = compute_fusion_flags(
            acwr_status="optimal", hrv_state="balanced", form_delta_pct=1.0
        )
        assert all(value is False for value in flags.values())

    def test_fusion_handles_none_signals(self) -> None:
        flags = compute_fusion_flags(
            acwr_status=None, hrv_state=None, form_delta_pct=None
        )
        assert all(value is False for value in flags.values())


@pytest.mark.unit
class TestComputeTrendHeadlineMetrics:
    def test_headline_extracts_expected_keys(self) -> None:
        context = {
            "load_trend": {
                "weeks": [
                    {"week_start": "2026-06-01", "load_km": 30.0},
                    {"week_start": "2026-06-08", "load_km": 35.0},
                    {"week_start": "2026-06-15", "load_km": 40.0},
                ]
            },
            "acwr": {"status": "optimal"},
            "recovery_trend": {"hrv": {"status": "balanced", "under_recovery": False}},
        }
        result = compute_trend_headline_metrics(context)

        assert "load_delta_pct" in result
        assert "build_weeks" in result
        assert "fusion_flags" in result
        # (40 - 35) / 35 * 100 ≈ 14.3; three increasing weeks -> streak 3.
        assert result["load_delta_pct"] == pytest.approx(14.3)
        assert result["build_weeks"] == 3
        assert result["fusion_flags"]["high_load_low_recovery"] is False

    def test_headline_empty_context(self) -> None:
        result = compute_trend_headline_metrics({})

        # Required keys are present, filled with null where data is missing.
        assert result["load_delta_pct"] is None
        assert result["build_weeks"] is None
        assert "fusion_flags" in result
        assert all(value is False for value in result["fusion_flags"].values())

    @staticmethod
    def _longest_run_context(longest_run_sec: list[int]) -> dict:
        return {
            "load_trend": {
                "weeks": [
                    {"load_km": 40.0, "longest_run_sec": s} for s in longest_run_sec
                ]
            }
        }

    def test_headline_deload_prescription_when_cutback_due(self) -> None:
        # Three straight >=+3% long-run extensions -> cutback due.
        result = compute_trend_headline_metrics(
            self._longest_run_context([3250, 7819, 8125, 8562])
        )

        assert result["cutback_due_long_run"] is True
        assert result["deload_prescription"] == {
            "long_run_reduction_pct": [30, 40],
            "weekly_volume_reduction_pct": [20, 30],
            "quality_sessions": 0,
        }

    def test_headline_deload_prescription_none_when_not_due(self) -> None:
        # 7480 is a hold, so the streak is 2 -> no cutback yet.
        result = compute_trend_headline_metrics(
            self._longest_run_context([7200, 7500, 7480, 7800])
        )

        assert result["cutback_due_long_run"] is False
        assert result["deload_prescription"] is None
