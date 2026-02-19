"""Tests for text_generator module.

This module tests the Japanese evaluation text generation for form metrics.
"""

import pytest

from garmin_mcp.form_baseline.text_generator import (
    generate_evaluation_text,
    generate_overall_text,
)


@pytest.mark.unit
class TestGenerateEvaluationText:
    """Test cases for generate_evaluation_text function."""

    # GCT Tests
    def test_gct_significantly_low_over_5pct(self):
        """GCT delta < -5% should generate significantly low evaluation."""
        text = generate_evaluation_text(
            metric="gct",
            actual=258.0,
            expected=275.0,
            delta_pct=-6.2,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "258" in text or "258.0" in text
        assert "275" in text or "275.0" in text
        assert "外れ" in text or "短く" in text
        assert "★★☆☆☆" in text

    def test_gct_slightly_low_2_to_5pct(self):
        """GCT -5% < delta < -2% should generate slightly low evaluation."""
        text = generate_evaluation_text(
            metric="gct",
            actual=258.0,
            expected=264.0,
            delta_pct=-2.3,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "258" in text
        assert "264" in text
        assert "やや外れ" in text or "短く" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_gct_ideal_within_2pct(self):
        """GCT abs(delta) <= 2% should generate ideal evaluation."""
        text = generate_evaluation_text(
            metric="gct",
            actual=258.0,
            expected=261.0,
            delta_pct=1.2,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "258" in text
        assert "261" in text
        assert "理想範囲" in text or "適切" in text
        assert "★★★☆☆" in text

    def test_gct_slightly_long_2_to_5pct(self):
        """GCT 2% < delta <= 5% should generate slightly long evaluation."""
        text = generate_evaluation_text(
            metric="gct",
            actual=264.0,
            expected=258.0,
            delta_pct=2.3,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "264" in text
        assert "258" in text
        assert "やや外れ" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_gct_needs_improvement_over_5pct(self):
        """GCT delta > 5% should generate needs improvement evaluation."""
        text = generate_evaluation_text(
            metric="gct",
            actual=280.0,
            expected=258.0,
            delta_pct=8.5,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "280" in text
        assert "258" in text
        assert "外れ" in text or "不安定" in text
        assert "★★☆☆☆" in text

    # VO Tests
    def test_vo_significantly_low_over_5pct(self):
        """VO delta < -5% should generate significantly low evaluation."""
        text = generate_evaluation_text(
            metric="vo",
            actual=6.5,
            expected=7.0,
            delta_pct=-7.1,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "6.5" in text
        assert "7.0" in text or "7" in text
        assert "外れ" in text or "小さく" in text
        assert "★★☆☆☆" in text

    def test_vo_slightly_low_2_to_5pct(self):
        """VO -5% < delta < -2% should generate slightly low evaluation."""
        text = generate_evaluation_text(
            metric="vo",
            actual=6.8,
            expected=7.0,
            delta_pct=-2.9,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "6.8" in text
        assert "7.0" in text or "7" in text
        assert "やや外れ" in text or "小さく" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_vo_ideal_within_2pct(self):
        """VO abs(delta) <= 2% should generate ideal evaluation."""
        text = generate_evaluation_text(
            metric="vo",
            actual=7.0,
            expected=7.1,
            delta_pct=-1.4,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "7.0" in text or "7" in text
        assert "7.1" in text
        assert "理想範囲" in text or "適切" in text
        assert "★★★☆☆" in text

    def test_vo_slightly_high_2_to_5pct(self):
        """VO 2% < delta <= 5% should generate slightly high evaluation."""
        text = generate_evaluation_text(
            metric="vo",
            actual=7.3,
            expected=7.0,
            delta_pct=4.3,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "7.3" in text
        assert "7.0" in text or "7" in text
        assert "やや外れ" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_vo_needs_improvement_over_5pct(self):
        """VO delta > 5% should generate needs improvement evaluation."""
        text = generate_evaluation_text(
            metric="vo",
            actual=9.5,
            expected=7.0,
            delta_pct=35.7,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "9.5" in text
        assert "7.0" in text or "7" in text
        assert "外れ" in text or "不安定" in text
        assert "★★☆☆☆" in text

    # VR Tests
    def test_vr_significantly_low_over_5pct(self):
        """VR delta < -5% should generate significantly low evaluation."""
        text = generate_evaluation_text(
            metric="vr",
            actual=6.5,
            expected=7.0,
            delta_pct=-7.1,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "6.5" in text
        assert "7.0" in text or "7" in text
        assert "外れ" in text or "低く" in text
        assert "★★☆☆☆" in text

    def test_vr_slightly_low_2_to_5pct(self):
        """VR -5% < delta < -2% should generate slightly low evaluation."""
        text = generate_evaluation_text(
            metric="vr",
            actual=6.8,
            expected=7.0,
            delta_pct=-2.9,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "6.8" in text
        assert "7.0" in text or "7" in text
        assert "やや外れ" in text or "低く" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_vr_ideal_within_2pct(self):
        """VR abs(delta) <= 2% should generate ideal evaluation."""
        text = generate_evaluation_text(
            metric="vr",
            actual=7.0,
            expected=7.1,
            delta_pct=-1.4,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "7.0" in text or "7" in text
        assert "7.1" in text
        assert "理想範囲" in text or "適切" in text
        assert "★★★☆☆" in text

    def test_vr_slightly_high_2_to_5pct(self):
        """VR 2% < delta <= 5% should generate slightly high evaluation."""
        text = generate_evaluation_text(
            metric="vr",
            actual=7.3,
            expected=7.0,
            delta_pct=4.3,
            pace_s_per_km=431.0,
            star_rating="★★★☆☆",
            score=3.0,
        )
        assert "7.3" in text
        assert "7.0" in text or "7" in text
        assert "やや外れ" in text or "ズレ" in text
        assert "★★★☆☆" in text

    def test_vr_needs_improvement_over_5pct(self):
        """VR delta > 5% should generate needs improvement evaluation."""
        text = generate_evaluation_text(
            metric="vr",
            actual=9.5,
            expected=7.0,
            delta_pct=35.7,
            pace_s_per_km=431.0,
            star_rating="★★☆☆☆",
            score=2.0,
        )
        assert "9.5" in text
        assert "7.0" in text or "7" in text
        assert "外れ" in text or "不安定" in text
        assert "★★☆☆☆" in text


@pytest.mark.unit
class TestGenerateOverallText:
    """Test cases for generate_overall_text function."""

    def test_overall_text_perfect(self):
        """Test overall text generation for perfect score."""
        evaluation = {
            "overall_score": 5.0,
            "overall_star_rating": "★★★★★",
        }
        text = generate_overall_text(evaluation)
        assert "★★★★★" in text
        assert "5.0" in text
        assert "総合評価" in text

    def test_overall_text_good(self):
        """Test overall text generation for good score."""
        evaluation = {
            "overall_score": 4.5,
            "overall_star_rating": "★★★★☆",
        }
        text = generate_overall_text(evaluation)
        assert "★★★★☆" in text
        assert "4.5" in text
        assert "総合評価" in text

    def test_overall_text_average(self):
        """Test overall text generation for average score."""
        evaluation = {
            "overall_score": 3.0,
            "overall_star_rating": "★★★☆☆",
        }
        text = generate_overall_text(evaluation)
        assert "★★★☆☆" in text
        assert "3.0" in text
        assert "総合評価" in text

    def test_overall_text_needs_improvement(self):
        """Test overall text generation for low score."""
        evaluation = {
            "overall_score": 2.0,
            "overall_star_rating": "★★☆☆☆",
        }
        text = generate_overall_text(evaluation)
        assert "★★☆☆☆" in text
        assert "2.0" in text
        assert "総合評価" in text
