"""form_baseline.trainer model classes and fitters: GCTPowerModel, LinearModel, fit_gct_power, fit_linear (cadence slope clamp, outlier removal)."""

import numpy as np
import pandas as pd
import pytest

from garmin_mcp.form_baseline.scorer import (
    _compute_penalty,
    _extrapolation_factor,
    compute_star_rating,
)
from garmin_mcp.form_baseline.trainer import (
    GCTPowerModel,
    LinearModel,
    _effective_speed_range,
    fit_gct_power,
    fit_linear,
)


@pytest.mark.unit
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


@pytest.mark.unit
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

    def test_linear_model_predict_flat_returns_intercept(self):
        """A degenerate (flat) model returns the intercept at any speed."""
        model = LinearModel(
            a=178.0,
            b=0.0,
            rmse=4.0,
            n_samples=150,
            speed_range=(2.0, 4.0),
            degenerate=True,
        )

        assert model.predict(3.33) == 178.0
        assert model.predict(2.0) == 178.0


@pytest.mark.unit
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
        """Test GCT power model with noisy data.

        Speed is the predictor and GCT the response, so the scatter is put on
        GCT. (Perturbing speed instead would inject error into the regressor
        and bias any fit -- that was how this test used to be written, back
        when the model was fitted in the speed direction.)
        """
        rng = np.random.default_rng(42)
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.linspace(3.1, 4.2, 20)
        gct_values = np.exp((np.log(speed_values) - alpha_true) / d_true)
        # Add multiplicative noise to the measured GCT
        gct_values = gct_values * np.exp(rng.normal(0, 0.02, size=len(gct_values)))

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        model = fit_gct_power(df, fallback_ransac=False)

        # Should still be monotonic
        assert model.d < 0
        # Should be reasonably close to true values (relaxed tolerance for noisy data)
        assert abs(model.alpha - alpha_true) < 0.4
        assert abs(model.d - d_true) < 0.1

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

    @staticmethod
    def _noisy_gct_frame(
        k_true: float = -0.30,
        c_true: float = 300.0,
        sigma_log: float = 0.03,
        n: int = 200,
        v_lo: float = 1.9,
        v_hi: float = 2.6,
    ) -> pd.DataFrame:
        """Synthetic splits following gct = c * v**k with noise on GCT.

        Noise lives on GCT because that is where the measurement scatter
        actually is: at a given pace the same runner's contact time varies.
        """
        rng = np.random.default_rng(20260909)
        speed = rng.uniform(v_lo, v_hi, size=n)
        gct = c_true * speed**k_true * np.exp(rng.normal(0.0, sigma_log, size=n))
        return pd.DataFrame({"gct_ms": gct, "speed_mps": speed})

    def test_fit_gct_power_recovers_known_exponent_with_noise(self):
        """The effective GCT-vs-speed exponent 1/d matches the generating one.

        Regression guard for #1088: fitting log(speed) on log(GCT) and
        inverting it recovers roughly -0.45 here instead of -0.30, i.e. an
        expectation curve far too steep at fast paces.
        """
        df = self._noisy_gct_frame()

        model = fit_gct_power(df, fallback_ransac=False)

        assert model.d < 0
        assert abs(1.0 / model.d - (-0.30)) < 0.05

    def test_fit_gct_power_is_unbiased_at_range_edges(self):
        """No systematic residual tilt at the fast end of the training range."""
        df = self._noisy_gct_frame()
        model = fit_gct_power(df, fallback_ransac=False)

        cutoff = df["speed_mps"].quantile(0.9)
        fast = df[df["speed_mps"] >= cutoff]
        predicted = np.array([model.predict_inverse(v) for v in fast["speed_mps"]])
        residual_pct = ((fast["gct_ms"].values - predicted) / predicted) * 100.0

        assert abs(float(np.mean(residual_pct))) < 1.5

    def test_fit_gct_power_rmse_maps_to_log_gct_sigma(self):
        """``rmse / abs(d)`` is the log-GCT residual sigma the scorer expects."""
        df = self._noisy_gct_frame(sigma_log=0.03)

        model = fit_gct_power(df, fallback_ransac=False)

        assert abs(model.rmse / abs(model.d) - 0.03) < 0.01

    def test_fit_gct_power_insufficient_data(self):
        """Test error with insufficient data."""
        df = pd.DataFrame({"gct_ms": [200, 250], "speed_mps": [3.0, 2.8]})

        # Should raise ValueError (need more samples)
        with pytest.raises((ValueError, Exception)):
            fit_gct_power(df, fallback_ransac=False)


@pytest.mark.unit
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

    def test_fit_linear_cadence_positive_slope(self):
        """Cadence increases with speed -> b > 0."""
        # Synthetic data: cadence = 160.0 + 5.0 * speed (positive slope)
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
        a_true = 160.0
        b_true = 5.0
        cadence_values = a_true + b_true * speed_values

        df = pd.DataFrame({"cadence_value": cadence_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="cadence")

        # Faster speed -> higher cadence: positive slope
        assert model.b > 0
        assert abs(model.a - a_true) < 0.5
        assert abs(model.b - b_true) < 0.5
        assert model.n_samples == 6

    def test_fit_linear_cadence_outlier_removal(self):
        """Cadence values below 140spm / above 210spm are removed."""
        # 6 valid points plus 2 outliers (one < 140, one > 210)
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 3.2, 3.8])
        cadence_values = np.array(
            [172.0, 175.0, 178.0, 181.0, 184.0, 187.0, 130.0, 215.0]
        )

        df = pd.DataFrame({"cadence_value": cadence_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="cadence")

        # Two outliers removed -> 6 valid samples remain
        assert model.n_samples == 6
        # Speed range should reflect only valid rows (3.2 and 3.8 kept, but
        # their cadence outliers removed them) -> min 2.5, max 5.0
        assert model.speed_range[0] == 2.5
        assert model.speed_range[1] == 5.0

    def test_fit_linear_cadence_clamps_negative_slope(self):
        """An inverted cadence slope is suppressed to a flat model (#873)."""
        # Cadence falling with speed is physiologically backwards.
        df = pd.DataFrame(
            {"cadence_value": [180.0, 174.0], "speed_mps": [2.0, 3.0]},
        )

        model = fit_linear(df, metric="cadence")

        assert model.b == 0.0
        assert model.degenerate is True
        # Intercept-only least-squares solution = sample mean
        assert abs(model.a - 177.0) < 0.01

    def test_fit_linear_cadence_keeps_positive_slope(self):
        """A physiologically correct cadence slope is preserved unchanged."""
        df = pd.DataFrame(
            {"cadence_value": [175.0, 185.0], "speed_mps": [2.0, 3.0]},
        )

        model = fit_linear(df, metric="cadence")

        assert model.b > 0
        assert model.degenerate is False

    def test_fit_linear_vo_negative_slope_preserved(self):
        """VO legitimately falls with speed: the clamp must not apply."""
        df = pd.DataFrame(
            {"vo_value": [9.0, 7.0], "speed_mps": [2.0, 3.0]},
        )

        model = fit_linear(df, metric="vo")

        assert model.b < 0
        assert model.degenerate is False


def _self_included_window() -> pd.DataFrame:
    """A summer window: 100 easy splits plus one fast workout's 4 splits.

    Mirrors the real 2026-07-31..09-30 baseline, where every split above
    2.55 m/s came from the very activity being scored (#1096).
    """
    rng = np.random.default_rng(1096)
    # Matches the real window's spread (p05 1.976 / p95 2.410, raw max 2.99)
    easy = rng.uniform(1.95, 2.45, size=273)
    fast = np.array([2.65, 2.80, 2.93, 2.99])
    speed = np.concatenate([easy, fast])
    return pd.DataFrame(
        {
            "speed_mps": speed,
            "gct_ms": 300.0 * speed**-0.30,
            "vr_value": 14.4 - 2.15 * speed,
            "vo_value": 6.5 + 0.28 * speed,
        }
    )


@pytest.mark.unit
class TestEffectiveSpeedRange:
    """speed_range reports the trusted band, not the furthest point (#1096)."""

    def test_effective_speed_range_uses_percentiles(self):
        """A lone fast outlier must not stretch the reported range."""
        speeds = np.append(np.linspace(2.0, 2.5, 100), 3.5)

        low, high = _effective_speed_range(speeds)

        assert high < 2.6
        assert low >= 2.0

    def test_effective_speed_range_falls_back_for_small_sample(self):
        """Below the sample floor the percentile band is meaningless."""
        speeds = np.linspace(2.0, 3.0, 10)

        assert _effective_speed_range(speeds) == (2.0, 3.0)

    def test_effective_speed_range_falls_back_when_band_collapses(self):
        """Identical speeds give p05 == p95, so report the raw range."""
        speeds = np.full(50, 2.5)

        assert _effective_speed_range(speeds) == (2.5, 2.5)

    def test_fit_gct_power_speed_range_excludes_lone_fast_point(self):
        """GCT model's range reflects where the data actually is."""
        df = _self_included_window()

        model = fit_gct_power(df[["gct_ms", "speed_mps"]], fallback_ransac=False)

        assert model.speed_range[1] < 2.6

    def test_fit_linear_speed_range_excludes_lone_fast_point(self):
        """VR model's range likewise."""
        df = _self_included_window()

        model = fit_linear(df[["vr_value", "speed_mps"]], metric="vr")

        assert model.speed_range[1] < 2.6

    @pytest.mark.integration
    def test_extrapolation_guard_fires_for_self_included_fast_run(self):
        """The guard fires at 2.719 m/s and lifts a +3.2% VR by a full star.

        With the raw min/max range (2.99, stretched by the scored activity's
        own splits) the guard stayed silent and the same deviation was scored
        at full confidence.
        """
        df = _self_included_window()
        model = fit_linear(df[["vr_value", "speed_mps"]], metric="vr")

        factor = _extrapolation_factor(model, 2.719)
        assert factor > 2.0

        raw_range_model = LinearModel(
            a=model.a,
            b=model.b,
            rmse=model.rmse,
            n_samples=model.n_samples,
            speed_range=(
                float(df["speed_mps"].min()),
                float(df["speed_mps"].max()),
            ),
        )
        assert _extrapolation_factor(raw_range_model, 2.719) == 1.0

        delta_pct = 3.2
        sigma_pct = 1.47
        guarded = compute_star_rating(
            penalty=_compute_penalty("vr", delta_pct, sigma_pct * factor),
            delta_pct=delta_pct,
        )
        unguarded = compute_star_rating(
            penalty=_compute_penalty("vr", delta_pct, sigma_pct),
            delta_pct=delta_pct,
        )
        assert guarded["score"] >= unguarded["score"] + 1.0
