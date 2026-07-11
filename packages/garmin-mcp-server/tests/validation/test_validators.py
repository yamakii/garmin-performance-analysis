"""Unit tests for garmin_mcp.validation.validators pure functions."""

import pytest

from garmin_mcp.validation.validators import (
    check_form_trend_consistency,
    check_narration_numeric_consistency,
    check_star_weighting_consistency,
)

# Weighted average = 4.0*0.4 + 3.0*0.3 + 5.0*0.2 + 2.0*0.1 = 3.7
_BREAKDOWN_3_7 = {
    "axis_scores": {
        "effort": 4.0,
        "performance": 3.0,
        "efficiency": 5.0,
        "execution": 2.0,
    },
    "weights": {
        "effort": 0.4,
        "performance": 0.3,
        "efficiency": 0.2,
        "execution": 0.1,
    },
}

# Weighted mean = 2.5*0.4 + 3.0*0.25 + 4.0*0.2 + 4.0*0.15 = 3.15 (an X.X5
# boundary). round(3.15, 1) -> 3.1 (half-to-even) but the LLM half-up rounds
# to 3.2; both are within 0.05 of the true mean (Issue #859, activity
# 23534377199 environment section).
_BREAKDOWN_3_15 = {
    "axis_scores": {
        "temperature": 2.5,
        "humidity": 3.0,
        "terrain": 4.0,
        "wind": 4.0,
    },
    "weights": {
        "temperature": 0.4,
        "humidity": 0.25,
        "terrain": 0.2,
        "wind": 0.15,
    },
}


@pytest.mark.unit
class TestCheckFormTrendConsistency:
    """Tests for check_form_trend_consistency()."""

    def test_form_trend_skip_with_baseline_fails(self):
        ok, errors = check_form_trend_consistency(
            "ベースラインデータが含まれていないため省略します。",
            True,
        )
        assert ok is False
        assert errors

    def test_form_trend_valid_comparison_passes(self):
        ok, errors = check_form_trend_consistency(
            "1ヶ月前との比較ではGCTが-0.14改善し、フォーム効率は向上傾向です。",
            True,
        )
        assert ok is True
        assert errors == []

    def test_form_trend_skip_without_baseline_passes(self):
        ok, errors = check_form_trend_consistency(
            "ベースラインデータが不足のため省略します。",
            False,
        )
        assert ok is True
        assert errors == []

    def test_form_trend_empty_with_baseline_fails(self):
        ok, errors = check_form_trend_consistency("", True)
        assert ok is False
        assert errors


@pytest.mark.unit
class TestCheckNarrationNumericConsistency:
    """Tests for check_narration_numeric_consistency()."""

    def test_narration_score_within_range_ok(self):
        ok, errors = check_narration_numeric_consistency(
            {"integrated_score": 85.5, "star_rating": "★★★★☆ 4.2/5.0"}
        )
        assert ok is True
        assert errors == []

    def test_narration_score_out_of_range_fails(self):
        ok, errors = check_narration_numeric_consistency(
            {"integrated_score": 120, "star_rating": "★★★★☆ 4.2/5.0"}
        )
        assert ok is False
        assert errors

    def test_narration_star_over_5_fails(self):
        ok, errors = check_narration_numeric_consistency(
            {"integrated_score": 85.5, "star_rating": "★★★★★ 6.5/5.0"}
        )
        assert ok is False
        assert errors

    def test_narration_star_malformed_fails(self):
        ok, errors = check_narration_numeric_consistency(
            {"integrated_score": 85.5, "star_rating": "4.2/5"}
        )
        assert ok is False
        assert errors

    def test_narration_missing_fields_ok(self):
        ok, errors = check_narration_numeric_consistency(
            {"overall_assessment": "良好なペース配分"}
        )
        assert ok is True
        assert errors == []


@pytest.mark.unit
class TestCheckStarWeightingConsistency:
    """Tests for check_star_weighting_consistency()."""

    def test_check_star_weighting_pass(self):
        ok, reason = check_star_weighting_consistency(
            "summary",
            {
                "star_rating": "★★★★☆ 3.7/5.0",
                "star_rating_breakdown": _BREAKDOWN_3_7,
            },
        )
        assert ok is True
        assert reason is None

    def test_guard_passes_consistent_breakdown(self):
        # Regression: a consistent breakdown for every weighted section passes.
        for section_type in ("summary", "phase", "environment"):
            ok, reason = check_star_weighting_consistency(
                section_type,
                {
                    "star_rating": "★★★★☆ 3.7/5.0",
                    "star_rating_breakdown": _BREAKDOWN_3_7,
                },
            )
            assert ok is True, section_type
            assert reason is None, section_type

    def test_guard_rejects_missing_breakdown_for_weighted_sections(self):
        # Issue #751: fail-closed. Missing breakdown on a weighted-star section
        # must be rejected (not silently passed).
        for section_type in ("summary", "phase", "environment"):
            ok, reason = check_star_weighting_consistency(
                section_type,
                {"star_rating": "★★★★☆ 4.2/5.0"},
            )
            assert ok is False, section_type
            assert reason is not None
            assert "star_rating_breakdown" in reason
            assert section_type in reason

    def test_guard_still_passes_non_weighted_sections_without_breakdown(self):
        # efficiency / split carry no weighted rating -> breakdown not required.
        for section_type in ("efficiency", "split"):
            ok, reason = check_star_weighting_consistency(
                section_type,
                {"highlights": "1kmごとのペースは安定していました。"},
            )
            assert ok is True, section_type
            assert reason is None, section_type

    def test_check_star_weighting_fail_mismatch(self):
        ok, reason = check_star_weighting_consistency(
            "summary",
            {
                "star_rating": "★★★★☆ 4.5/5.0",
                "star_rating_breakdown": _BREAKDOWN_3_7,
            },
        )
        assert ok is False
        assert reason is not None
        assert "3.7" in reason
        assert "4.5" in reason

    def test_check_star_weighting_skips_without_scores(self):
        ok, reason = check_star_weighting_consistency(
            "split",
            {"highlights": "1kmごとのペースは安定していました。"},
        )
        assert ok is True
        assert reason is None

    def test_check_star_weighting_rejects_summary_without_breakdown(self):
        # Issue #751: previously fail-open; now fail-closed for weighted sections.
        ok, reason = check_star_weighting_consistency(
            "summary",
            {"star_rating": "★★★★☆ 4.2/5.0", "integrated_score": 85.0},
        )
        assert ok is False
        assert reason is not None
        assert "star_rating_breakdown" in reason

    def test_check_star_weighting_phase_numeric_stated_pass(self):
        ok, reason = check_star_weighting_consistency(
            "phase",
            {"star_rating_breakdown": {**_BREAKDOWN_3_7, "star_rating": 3.7}},
        )
        assert ok is True
        assert reason is None

    def test_check_star_weighting_environment_numeric_stated_fail(self):
        ok, reason = check_star_weighting_consistency(
            "environment",
            {"star_rating_breakdown": {**_BREAKDOWN_3_7, "star_rating": 4.5}},
        )
        assert ok is False
        assert reason is not None

    def test_guard_accepts_half_step_boundary_rounding(self):
        # Issue #859: raw weighted mean is exactly 3.15 (an X.X5 boundary).
        # The LLM half-up rounds to 3.2, the old validator round()d to 3.1;
        # both are correct 1-decimal displays and must pass against the
        # unrounded mean (each within 0.05 of 3.15).
        for stated in ("★★★☆☆ 3.2/5.0", "★★★☆☆ 3.1/5.0"):
            ok, reason = check_star_weighting_consistency(
                "environment",
                {
                    "star_rating": stated,
                    "star_rating_breakdown": _BREAKDOWN_3_15,
                },
            )
            assert ok is True, stated
            assert reason is None, stated

    def test_guard_rejects_real_arithmetic_error(self):
        # Issue #859: 3.5 is 0.35 off the true mean (3.15) -> genuine error.
        ok, reason = check_star_weighting_consistency(
            "environment",
            {
                "star_rating": "★★★☆☆ 3.5/5.0",
                "star_rating_breakdown": _BREAKDOWN_3_15,
            },
        )
        assert ok is False
        assert reason is not None
        assert "3.5" in reason

    def test_check_star_weighting_malformed_breakdown_fails(self):
        breakdown = {
            "axis_scores": {"effort": 4.0, "performance": 3.0},
            "weights": {"effort": 0.4},
            "star_rating": 3.7,
        }
        ok, reason = check_star_weighting_consistency(
            "summary", {"star_rating_breakdown": breakdown}
        )
        assert ok is False
        assert reason is not None
        assert "malformed" in reason
