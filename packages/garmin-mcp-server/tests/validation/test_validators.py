"""Unit tests for garmin_mcp.validation.validators pure functions."""

import pytest

from garmin_mcp.validation.validators import (
    check_form_trend_consistency,
    check_narration_numeric_consistency,
)


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
