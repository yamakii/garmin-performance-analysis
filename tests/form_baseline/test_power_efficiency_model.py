"""Tests for PowerEfficiencyModel.

Tests linear regression model: speed_mps = power_a + power_b * power_wkg
"""

import numpy as np
import pytest


@pytest.mark.unit
def test_power_efficiency_model_fit():
    """W/kgから速度への線形回帰."""
    from tools.form_baseline.power_efficiency_model import PowerEfficiencyModel

    # Sample data: power_wkg vs speed
    # Relationship: speed = 1.2 + 0.6 * power_wkg
    power_wkg_values = [3.0, 3.5, 4.0, 4.5, 5.0]
    speeds = [3.0, 3.3, 3.6, 3.9, 4.2]

    model = PowerEfficiencyModel()
    model.fit(power_wkg_values, speeds)

    # Check coefficients (approximately)
    assert (
        abs(model.power_a - 1.2) < 0.01
    ), f"power_a should be ~1.2, got {model.power_a}"
    assert (
        abs(model.power_b - 0.6) < 0.01
    ), f"power_b should be ~0.6, got {model.power_b}"
    assert (
        model.power_rmse < 0.001
    ), f"RMSE should be very small, got {model.power_rmse}"


@pytest.mark.unit
def test_power_efficiency_model_predict():
    """予測速度計算."""
    from tools.form_baseline.power_efficiency_model import PowerEfficiencyModel

    model = PowerEfficiencyModel()
    model.power_a = 1.5
    model.power_b = 0.6

    # Predict speed for power_wkg = 4.0
    speed_pred = model.predict(4.0)
    expected = 1.5 + 0.6 * 4.0  # 3.9 m/s

    assert abs(speed_pred - expected) < 0.01, f"Expected {expected}, got {speed_pred}"


@pytest.mark.unit
def test_power_efficiency_model_with_real_data():
    """実データでの動作確認."""
    from tools.form_baseline.power_efficiency_model import PowerEfficiencyModel

    # Realistic running data
    # power_wkg ranges from 3.5 to 5.0 W/kg
    # speed ranges from 3.0 to 4.5 m/s
    np.random.seed(42)
    power_wkg_values = np.linspace(3.5, 5.0, 20)
    speeds = 1.0 + 0.7 * power_wkg_values + np.random.normal(0, 0.1, 20)

    model = PowerEfficiencyModel()
    model.fit(power_wkg_values.tolist(), speeds.tolist())

    # Check model is reasonable
    assert (
        0.5 < model.power_a < 2.0
    ), f"power_a should be reasonable, got {model.power_a}"
    assert (
        0.5 < model.power_b < 1.0
    ), f"power_b should be reasonable, got {model.power_b}"
    assert model.power_rmse < 0.5, f"RMSE should be small, got {model.power_rmse}"

    # Check prediction
    speed_pred = model.predict(4.0)
    assert (
        3.0 < speed_pred < 4.5
    ), f"Predicted speed should be in realistic range, got {speed_pred}"


@pytest.mark.unit
def test_power_efficiency_model_insufficient_data():
    """データ不足時のエラー処理."""
    from tools.form_baseline.power_efficiency_model import PowerEfficiencyModel

    model = PowerEfficiencyModel()

    # Only 1 data point - cannot fit
    with pytest.raises(ValueError):
        model.fit([3.0], [3.0])


@pytest.mark.unit
def test_power_efficiency_model_zero_variance():
    """分散ゼロ（全値が同じ）の場合のエラー処理."""
    from tools.form_baseline.power_efficiency_model import PowerEfficiencyModel

    model = PowerEfficiencyModel()

    # All power_wkg values are the same
    with pytest.raises(ValueError):
        model.fit([4.0, 4.0, 4.0], [3.5, 3.6, 3.7])
