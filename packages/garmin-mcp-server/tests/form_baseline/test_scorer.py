"""Tests for form baseline scorer module."""

import pytest

from garmin_mcp.form_baseline.scorer import (
    _compute_consistency_adjustment,
    _compute_penalty,
    compute_star_rating,
    score_observation,
)


@pytest.mark.unit
class TestScoreObservation:
    """Tests for score_observation function."""

    def test_score_observation_perfect_match(self, sample_models: dict) -> None:
        """Test scoring when actual matches expected perfectly."""
        pace_s_per_km = 240.0
        speed_mps = 1000.0 / pace_s_per_km

        # Calculate expected values
        gct_exp = sample_models["gct"].predict_inverse(speed_mps)
        vo_exp = sample_models["vo"].predict(speed_mps)
        vr_exp = sample_models["vr"].predict(speed_mps)

        obs = {
            "pace_s_per_km": pace_s_per_km,
            "gct_ms": gct_exp,
            "vo_cm": vo_exp,
            "vr_pct": vr_exp,
        }

        result = score_observation(sample_models, obs)

        # Perfect match should have zero deltas and penalties
        assert abs(result["gct_delta_pct"]) < 0.1
        assert abs(result["vo_delta_cm"]) < 0.1
        assert abs(result["vr_delta_pct"]) < 0.1

        assert result["gct_penalty"] < 1.0
        assert result["vo_penalty"] < 1.0
        assert result["vr_penalty"] < 1.0

        # Score should be near 100
        assert result["score"] > 99.0

        # No improvement needed
        assert result["gct_needs_improvement"] is False
        assert result["vo_needs_improvement"] is False
        assert result["vr_needs_improvement"] is False

    def test_score_observation_slight_deviation(self, sample_models: dict) -> None:
        """Test scoring with slight deviation (degradation direction)."""
        pace_s_per_km = 240.0
        speed_mps = 1000.0 / pace_s_per_km

        gct_exp = sample_models["gct"].predict_inverse(speed_mps)
        vo_exp = sample_models["vo"].predict(speed_mps)
        vr_exp = sample_models["vr"].predict(speed_mps)

        # Deviate by 3% from expected (higher = degradation)
        obs = {
            "pace_s_per_km": pace_s_per_km,
            "gct_ms": gct_exp * 1.03,  # 3% higher
            "vo_cm": vo_exp + 0.2,  # 0.2cm higher
            "vr_pct": vr_exp * 1.03,  # 3% higher
        }

        result = score_observation(sample_models, obs)

        # Check deltas (all positive = degradation)
        assert 2.0 < result["gct_delta_pct"] < 4.0
        assert 0.15 < result["vo_delta_cm"] < 0.25
        assert 2.0 < result["vr_delta_pct"] < 4.0

        # Degradation penalties use full factor (1.0), same as before
        assert result["gct_penalty"] < 50.0
        assert 50.0 < result["vo_penalty"] <= 100.0  # 0.2cm is ~12% when vo_exp ~1.7cm
        assert result["vr_penalty"] < 50.0

        # Score should be moderate (lowered by high VO penalty)
        assert result["score"] > 40.0

    def test_score_observation_large_deviation(self, sample_models: dict) -> None:
        """Test scoring with large deviation requiring improvement."""
        pace_s_per_km = 240.0
        speed_mps = 1000.0 / pace_s_per_km

        gct_exp = sample_models["gct"].predict_inverse(speed_mps)
        vo_exp = sample_models["vo"].predict(speed_mps)
        vr_exp = sample_models["vr"].predict(speed_mps)

        # Deviate by 10% from expected (degradation direction)
        obs = {
            "pace_s_per_km": pace_s_per_km,
            "gct_ms": gct_exp * 1.10,  # 10% higher
            "vo_cm": vo_exp + 1.1,  # 1.1cm higher (ensures penalty > 20)
            "vr_pct": vr_exp * 1.10,  # 10% higher
        }

        result = score_observation(sample_models, obs)

        # Check deltas
        assert 9.0 < result["gct_delta_pct"] < 11.0
        assert 1.0 < result["vo_delta_cm"] < 1.2
        assert 9.0 < result["vr_delta_pct"] < 11.0

        # Penalties should be significant (>= 20)
        assert result["gct_penalty"] >= 20.0
        assert result["vo_penalty"] >= 20.0
        assert result["vr_penalty"] >= 20.0

        # Needs improvement flags should be set
        assert result["gct_needs_improvement"] is True
        assert result["vo_needs_improvement"] is True
        assert result["vr_needs_improvement"] is True

    def test_score_observation_includes_expectations(self, sample_models: dict) -> None:
        """Test that result includes all expectation fields."""
        obs = {
            "pace_s_per_km": 240.0,
            "gct_ms": 200.0,
            "vo_cm": 8.0,
            "vr_pct": 7.5,
        }

        result = score_observation(sample_models, obs)

        # Check expectation fields are present
        assert "pace" in result
        assert "speed_mps" in result
        assert "gct_ms_exp" in result
        assert "vo_cm_exp" in result
        assert "vr_pct_exp" in result

        # Check actual values are included
        assert result["gct_ms_actual"] == 200.0
        assert result["vo_cm_actual"] == 8.0
        assert result["vr_pct_actual"] == 7.5


@pytest.mark.unit
class TestComputeStarRating:
    """Tests for compute_star_rating function."""

    def test_five_star_excellent(self) -> None:
        """Test 5-star rating for excellent performance."""
        rating = compute_star_rating(penalty=8.0, delta_pct=4.0)

        # Use Unicode escapes to avoid encoding issues
        assert rating["star_rating"] == "\u2605\u2605\u2605\u2605\u2605"
        assert rating["score"] == 5.0
        assert rating["category"] == "excellent"

    def test_four_star_good(self) -> None:
        """Test 4-star rating for good performance."""
        rating = compute_star_rating(penalty=15.0, delta_pct=8.0)

        assert rating["star_rating"] == "\u2605\u2605\u2605\u2605\u2606"
        assert rating["score"] == 4.0
        assert rating["category"] == "good"

    def test_three_star_average(self) -> None:
        """Test 3-star rating for average performance."""
        rating = compute_star_rating(penalty=30.0, delta_pct=15.0)

        assert rating["star_rating"] == "\u2605\u2605\u2605\u2606\u2606"
        assert rating["score"] == 3.0
        assert rating["category"] == "average"

    def test_two_star_below_average(self) -> None:
        """Test 2-star rating for below average performance."""
        rating = compute_star_rating(penalty=50.0, delta_pct=25.0)

        assert rating["star_rating"] == "\u2605\u2605\u2606\u2606\u2606"
        assert rating["score"] == 2.0
        assert rating["category"] == "below_average"

    def test_one_star_poor(self) -> None:
        """Test 1-star rating for poor performance."""
        rating = compute_star_rating(penalty=70.0, delta_pct=35.0)

        assert rating["star_rating"] == "\u2605\u2606\u2606\u2606\u2606"
        assert rating["score"] == 1.0
        assert rating["category"] == "poor"

    def test_boundary_case_five_to_four(self) -> None:
        """Test boundary between 5-star and 4-star (penalty-only)."""
        # Just below threshold
        rating1 = compute_star_rating(penalty=9.9, delta_pct=4.9)
        assert rating1["score"] == 5.0

        # Just above threshold (penalty only matters now)
        rating2 = compute_star_rating(penalty=10.1, delta_pct=4.0)
        assert rating2["score"] == 4.0

    def test_delta_pct_does_not_affect_rating(self) -> None:
        """Test that delta_pct is ignored in rating calculation.

        With asymmetric penalties, direction is encoded in the penalty value,
        so delta_pct should not independently affect the star rating.
        """
        # Large delta but low penalty should still get high stars
        rating = compute_star_rating(penalty=5.0, delta_pct=-20.0)
        assert rating["score"] == 5.0

        # Same penalty regardless of delta sign
        rating_pos = compute_star_rating(penalty=15.0, delta_pct=8.0)
        rating_neg = compute_star_rating(penalty=15.0, delta_pct=-8.0)
        assert rating_pos["score"] == rating_neg["score"]


@pytest.mark.unit
class TestComputePenalty:
    """Tests for _compute_penalty (asymmetric penalty calculation)."""

    def test_improvement_lower_penalty(self) -> None:
        """Improvement direction (delta < 0) should receive reduced penalty.

        VO -8.3% with factor 0.3: 8.3 * 0.3 * 10 = 24.9 (4 stars)
        vs symmetric: 8.3 * 1.0 * 10 = 83.0 (1 star)
        """
        penalty = _compute_penalty("vo", -8.3)
        assert 24.0 < penalty < 26.0  # ~24.9

    def test_degradation_full_penalty(self) -> None:
        """Degradation direction (delta > 0) should receive full penalty.

        VO +8.0% with factor 1.0: 8.0 * 1.0 * 10 = 80.0
        """
        penalty = _compute_penalty("vo", 8.0)
        assert penalty == pytest.approx(80.0)

    def test_vr_has_lowest_improvement_factor(self) -> None:
        """VR improvement factor (0.2) should be lower than GCT/VO (0.3).

        VR -5%: 5.0 * 0.2 * 10 = 10.0
        GCT -5%: 5.0 * 0.3 * 10 = 15.0
        """
        vr_penalty = _compute_penalty("vr", -5.0)
        gct_penalty = _compute_penalty("gct", -5.0)
        assert vr_penalty < gct_penalty
        assert vr_penalty == pytest.approx(10.0)
        assert gct_penalty == pytest.approx(15.0)

    def test_zero_delta_zero_penalty(self) -> None:
        """Zero delta should produce zero penalty."""
        for metric in ("gct", "vo", "vr"):
            assert _compute_penalty(metric, 0.0) == 0.0

    def test_penalty_clamped_to_100(self) -> None:
        """Penalty should never exceed 100."""
        penalty = _compute_penalty("gct", 20.0)  # 20 * 1.0 * 10 = 200 -> clamped
        assert penalty == 100.0

    def test_gct_improvement_penalty(self) -> None:
        """GCT improvement (shorter contact time) should use factor 0.3."""
        penalty = _compute_penalty("gct", -3.0)
        assert penalty == pytest.approx(9.0)  # 3.0 * 0.3 * 10


@pytest.mark.unit
class TestConsistencyAdjustment:
    """Tests for _compute_consistency_adjustment."""

    def test_consistency_bonus_all_improved(self) -> None:
        """All three metrics improved should give a positive bonus."""
        adj = _compute_consistency_adjustment(-3.0, -5.0, -4.0)
        assert adj > 0.0
        # (3+5+4)/3 * 0.5 = 2.0, capped at 5.0
        assert adj == pytest.approx(2.0)

    def test_consistency_bonus_capped(self) -> None:
        """Consistency bonus should not exceed 5.0."""
        adj = _compute_consistency_adjustment(-20.0, -25.0, -30.0)
        assert adj == 5.0

    def test_consistency_penalty_large_spread(self) -> None:
        """Large spread (>15%) between metrics should give -10 penalty."""
        # -10% vs +8% = 18% spread
        adj = _compute_consistency_adjustment(-10.0, -10.0, 8.0)
        assert adj == -10.0

    def test_consistency_penalty_medium_spread(self) -> None:
        """Medium spread (10-15%) should give -5 penalty."""
        # -5% vs +6% = 11% spread
        adj = _compute_consistency_adjustment(-5.0, 0.0, 6.0)
        assert adj == -5.0

    def test_consistency_penalty_small_spread(self) -> None:
        """Small spread (5-10%) should give -2 penalty."""
        # -3% vs +4% = 7% spread
        adj = _compute_consistency_adjustment(-3.0, 0.0, 4.0)
        assert adj == -2.0

    def test_consistency_no_adjustment(self) -> None:
        """Spread <= 5% with mixed directions should give 0."""
        adj = _compute_consistency_adjustment(-1.0, 1.0, 2.0)
        assert adj == 0.0

    def test_consistency_penalty_mixed_directions(self) -> None:
        """Mixed improvement/degradation with large spread gets penalized."""
        # VO improved -10%, VR degraded +6% = 16% spread (> 15)
        adj = _compute_consistency_adjustment(-5.0, -10.0, 6.0)
        assert adj == -10.0
