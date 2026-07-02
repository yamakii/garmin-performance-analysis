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

    def test_check_star_weighting_skips_summary_without_breakdown(self):
        ok, reason = check_star_weighting_consistency(
            "summary",
            {"star_rating": "★★★★☆ 4.2/5.0", "integrated_score": 85.0},
        )
        assert ok is True
        assert reason is None

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
