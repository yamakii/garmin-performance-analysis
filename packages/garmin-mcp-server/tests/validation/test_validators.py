"""Unit tests for garmin_mcp.validation.validators pure functions."""

import pytest

from garmin_mcp.validation.validators import check_form_trend_consistency


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
