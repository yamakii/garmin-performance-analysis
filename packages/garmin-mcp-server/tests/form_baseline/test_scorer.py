"""Tests for form baseline scorer module."""

import pytest

from garmin_mcp.form_baseline.scorer import compute_star_rating, score_observation
from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


class TestScoreObservation:
    """Tests for score_observation function."""

    @pytest.fixture
    def sample_models(self) -> dict:
        """Create sample trained models for testing."""
        return {
            "gct": GCTPowerModel(
                alpha=5.3,  # log(200) approx 5.3
                d=-0.15,
                rmse=5.0,
                n_samples=100,
                speed_range=(3.0, 5.0),
            ),
            "vo": LinearModel(
                a=10.0, b=-2.0, rmse=0.5, n_samples=100, speed_range=(3.0, 5.0)
            ),
            "vr": LinearModel(
                a=10.0, b=-0.5, rmse=0.3, n_samples=100, speed_range=(3.0, 5.0)
            ),
        }

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
        """Test scoring with slight deviation from expected."""
        pace_s_per_km = 240.0
        speed_mps = 1000.0 / pace_s_per_km

        gct_exp = sample_models["gct"].predict_inverse(speed_mps)
        vo_exp = sample_models["vo"].predict(speed_mps)
        vr_exp = sample_models["vr"].predict(speed_mps)

        # Deviate by 3% from expected
        obs = {
            "pace_s_per_km": pace_s_per_km,
            "gct_ms": gct_exp * 1.03,  # 3% higher
            "vo_cm": vo_exp + 0.2,  # 0.2cm higher
            "vr_pct": vr_exp * 1.03,  # 3% higher
        }

        result = score_observation(sample_models, obs)

        # Check deltas
        assert 2.0 < result["gct_delta_pct"] < 4.0
        assert 0.15 < result["vo_delta_cm"] < 0.25
        assert 2.0 < result["vr_delta_pct"] < 4.0

        # Penalties should be moderate (GCT/VR ~3%, but VO ~12% due to small expected value)
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

        # Deviate by 10% from expected
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
        """Test boundary between 5-star and 4-star."""
        # Just below threshold
        rating1 = compute_star_rating(penalty=9.9, delta_pct=4.9)
        assert rating1["score"] == 5.0

        # Just above threshold (penalty)
        rating2 = compute_star_rating(penalty=10.1, delta_pct=4.0)
        assert rating2["score"] == 4.0

        # Just above threshold (delta)
        rating3 = compute_star_rating(penalty=8.0, delta_pct=5.1)
        assert rating3["score"] == 4.0

    def test_negative_delta(self) -> None:
        """Test that negative delta is treated as absolute value."""
        rating_positive = compute_star_rating(penalty=15.0, delta_pct=8.0)
        rating_negative = compute_star_rating(penalty=15.0, delta_pct=-8.0)

        assert rating_positive["star_rating"] == rating_negative["star_rating"]
        assert rating_positive["score"] == rating_negative["score"]
        assert rating_positive["category"] == rating_negative["category"]
