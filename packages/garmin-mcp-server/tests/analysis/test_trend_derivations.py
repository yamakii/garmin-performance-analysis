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
)


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
