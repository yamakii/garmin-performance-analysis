"""Tests for form_baseline.trainer module."""

import numpy as np
import pandas as pd
import pytest

from tools.form_baseline.trainer import (
    GCTPowerModel,
    LinearModel,
    fit_gct_power,
    fit_linear,
)


class TestGCTPowerModel:
    """Test GCT power model dataclass."""

    def test_predict_inverse(self):
        """Test inverse prediction: speed -> GCT."""
        # Example: log(v) = 2.0 + (-0.5) * log(GCT)
        # For v=3.0 m/s: GCT = exp((log(3.0) - 2.0) / -0.5)
        model = GCTPowerModel(
            alpha=2.0, d=-0.5, rmse=0.1, n_samples=100, speed_range=(2.0, 5.0)
        )

        gct = model.predict_inverse(3.0)
        # Expected: exp((ln(3.0) - 2.0) / -0.5) ≈ exp((-0.901) / -0.5) ≈ exp(1.802) ≈ 6.06
        assert abs(gct - 6.06) < 0.1

    def test_predict_forward(self):
        """Test forward prediction: GCT -> speed."""
        model = GCTPowerModel(
            alpha=2.0, d=-0.5, rmse=0.1, n_samples=100, speed_range=(2.0, 5.0)
        )

        # For GCT=250: v = exp(2.0 + (-0.5) * log(250))
        speed = model.predict(250.0)
        expected = np.exp(2.0 + (-0.5) * np.log(250.0))
        assert abs(speed - expected) < 0.01


class TestLinearModel:
    """Test linear model dataclass."""

    def test_predict(self):
        """Test linear prediction: speed -> VO/VR."""
        # y = 10.0 + (-1.0) * v
        model = LinearModel(
            a=10.0, b=-1.0, rmse=0.5, n_samples=100, speed_range=(2.0, 5.0)
        )

        # For v=3.0: y = 10.0 - 3.0 = 7.0
        result = model.predict(3.0)
        assert abs(result - 7.0) < 0.01


class TestFitGCTPower:
    """Test GCT power model fitting."""

    def test_fit_gct_power_basic(self):
        """Test basic GCT power model fitting."""
        # Generate synthetic data with realistic running speeds (3-4 m/s)
        # Using formula: v = c * GCT^d, where c = exp(alpha)
        # For realistic data: alpha ~ 4.6, d ~ -0.6 gives speeds 3.1-4.0 m/s
        gct_values = np.array([200, 220, 240, 260, 280, 300])
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        model = fit_gct_power(df, fallback_ransac=False)

        # Check monotonicity (d < 0)
        assert model.d < 0

        # Check approximate coefficient recovery
        assert abs(model.alpha - alpha_true) < 0.2
        assert abs(model.d - d_true) < 0.2

        # Check metadata
        assert model.n_samples == 6
        assert model.speed_range[0] > 0
        assert model.speed_range[1] > model.speed_range[0]

    def test_fit_gct_power_with_noise(self):
        """Test GCT power model with noisy data."""
        np.random.seed(42)
        gct_values = np.linspace(200, 300, 20)
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))
        # Add noise
        speed_values += np.random.normal(0, 0.1, size=len(speed_values))

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        model = fit_gct_power(df, fallback_ransac=False)

        # Should still be monotonic
        assert model.d < 0
        # Should be reasonably close to true values (relaxed tolerance for noisy data)
        assert abs(model.alpha - alpha_true) < 0.8
        assert abs(model.d - d_true) < 0.3

    def test_fit_gct_power_ransac_fallback(self):
        """Test RANSAC fallback when Huber fails monotonicity."""
        # Create data that might cause Huber to fail (with outliers)
        np.random.seed(42)
        gct_values = np.array([200, 220, 240, 260, 280, 300, 180, 320])
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))
        # Add outliers
        speed_values[6] = 6.5  # High outlier
        speed_values[7] = 2.0  # Low outlier

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        # Should use RANSAC fallback if needed
        model = fit_gct_power(df, fallback_ransac=True)

        # Should still be monotonic
        assert model.d < 0

    def test_fit_gct_power_insufficient_data(self):
        """Test error with insufficient data."""
        df = pd.DataFrame({"gct_ms": [200, 250], "speed_mps": [3.0, 2.8]})

        # Should raise ValueError (need more samples)
        with pytest.raises((ValueError, Exception)):
            fit_gct_power(df, fallback_ransac=False)


class TestFitLinear:
    """Test linear model fitting."""

    def test_fit_linear_vo(self):
        """Test VO linear model fitting."""
        # Generate synthetic data: VO = 12.0 + (-1.5) * speed
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
        a_true = 12.0
        b_true = -1.5
        vo_values = a_true + b_true * speed_values

        df = pd.DataFrame({"vo_value": vo_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vo")

        # Check coefficient recovery
        assert abs(model.a - a_true) < 0.1
        assert abs(model.b - b_true) < 0.1

        # Check metadata
        assert model.n_samples == 6
        assert model.speed_range[0] == 2.5
        assert model.speed_range[1] == 5.0

    def test_fit_linear_vr(self):
        """Test VR linear model fitting."""
        # Generate synthetic data: VR = 15.0 + (-2.0) * speed
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5])
        a_true = 15.0
        b_true = -2.0
        vr_values = a_true + b_true * speed_values

        df = pd.DataFrame({"vr_value": vr_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vr")

        # Check coefficient recovery
        assert abs(model.a - a_true) < 0.1
        assert abs(model.b - b_true) < 0.1

    def test_fit_linear_with_noise(self):
        """Test linear model with noisy data."""
        np.random.seed(42)
        speed_values = np.linspace(2.0, 5.0, 30)
        a_true = 10.0
        b_true = -1.0
        vo_values = a_true + b_true * speed_values
        # Add noise
        vo_values += np.random.normal(0, 0.2, size=len(vo_values))

        df = pd.DataFrame({"vo_value": vo_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vo")

        # Should be close to true values
        assert abs(model.a - a_true) < 0.3
        assert abs(model.b - b_true) < 0.1

        # RMSE should be reasonable
        assert model.rmse < 0.5

    def test_fit_linear_insufficient_data(self):
        """Test error with insufficient data."""
        df = pd.DataFrame({"vo_value": [8.0], "speed_mps": [3.0]})

        # Should raise ValueError or have issues
        with pytest.raises((ValueError, Exception)):
            fit_linear(df, metric="vo")
