"""Tests for form baseline predictor module."""

import pytest

from garmin_mcp.form_baseline.predictor import predict_expectations


@pytest.mark.unit
class TestPredictExpectations:
    """Tests for predict_expectations function."""

    def test_predict_expectations_basic(self, sample_models: dict) -> None:
        """Test basic expectation prediction."""
        pace_s_per_km = 240.0  # 4:00/km

        result = predict_expectations(sample_models, pace_s_per_km)

        # Check all expected keys are present
        assert "pace" in result
        assert "speed_mps" in result
        assert "gct_ms_exp" in result
        assert "vo_cm_exp" in result
        assert "vr_pct_exp" in result

        # Verify pace is preserved
        assert result["pace"] == pace_s_per_km

        # Verify speed conversion (1000 / 240 = 4.166... m/s)
        assert abs(result["speed_mps"] - 4.1667) < 0.001

    def test_predict_expectations_fast_pace(self, sample_models: dict) -> None:
        """Test prediction at fast pace (3:30/km)."""
        pace_s_per_km = 210.0  # 3:30/km
        speed_mps = 1000.0 / pace_s_per_km  # ~4.76 m/s

        result = predict_expectations(sample_models, pace_s_per_km)

        # Verify speed
        assert abs(result["speed_mps"] - speed_mps) < 0.001

        # At higher speed, GCT should be lower (power model inverse)
        # Using predict_inverse: exp((log(speed) - alpha) / d)
        gct_expected = sample_models["gct"].predict_inverse(speed_mps)
        assert abs(result["gct_ms_exp"] - gct_expected) < 0.1

        # VO should decrease with speed (negative slope)
        vo_expected = -2.0 * speed_mps + 10.0
        assert abs(result["vo_cm_exp"] - vo_expected) < 0.1

        # VR should decrease with speed (negative slope)
        vr_expected = -0.5 * speed_mps + 10.0
        assert abs(result["vr_pct_exp"] - vr_expected) < 0.1

    def test_predict_expectations_slow_pace(self, sample_models: dict) -> None:
        """Test prediction at slow pace (5:00/km)."""
        pace_s_per_km = 300.0  # 5:00/km
        speed_mps = 1000.0 / pace_s_per_km  # ~3.33 m/s

        result = predict_expectations(sample_models, pace_s_per_km)

        # Verify speed
        assert abs(result["speed_mps"] - speed_mps) < 0.001

        # At lower speed, GCT should be higher
        gct_expected = sample_models["gct"].predict_inverse(speed_mps)
        assert abs(result["gct_ms_exp"] - gct_expected) < 0.1

        # VO increases at slower pace
        vo_expected = -2.0 * speed_mps + 10.0
        assert abs(result["vo_cm_exp"] - vo_expected) < 0.1

    def test_predict_expectations_model_keys(self, sample_models: dict) -> None:
        """Test that correct model methods are called."""
        pace_s_per_km = 240.0
        speed_mps = 1000.0 / pace_s_per_km

        result = predict_expectations(sample_models, pace_s_per_km)

        # Verify GCT uses power model inverse
        expected_gct = sample_models["gct"].predict_inverse(speed_mps)
        assert abs(result["gct_ms_exp"] - expected_gct) < 0.001

        # Verify VO uses linear model
        expected_vo = sample_models["vo"].predict(speed_mps)
        assert abs(result["vo_cm_exp"] - expected_vo) < 0.001

        # Verify VR uses linear model
        expected_vr = sample_models["vr"].predict(speed_mps)
        assert abs(result["vr_pct_exp"] - expected_vr) < 0.001

    def test_predict_expectations_consistency(self, sample_models: dict) -> None:
        """Test that multiple calls with same pace give same results."""
        pace_s_per_km = 240.0

        result1 = predict_expectations(sample_models, pace_s_per_km)
        result2 = predict_expectations(sample_models, pace_s_per_km)

        assert result1["gct_ms_exp"] == result2["gct_ms_exp"]
        assert result1["vo_cm_exp"] == result2["vo_cm_exp"]
        assert result1["vr_pct_exp"] == result2["vr_pct_exp"]
