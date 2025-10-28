"""Power Efficiency Model.

Linear regression model for power-to-speed relationship:
    speed_mps = power_a + power_b * power_wkg

Where:
- speed_mps: Running speed in meters per second
- power_wkg: Power per kg body weight (W/kg)
- power_a: Intercept coefficient
- power_b: Slope coefficient
"""

import numpy as np
from scipy import stats


class PowerEfficiencyModel:
    """Linear regression model for power efficiency.

    Model: speed = power_a + power_b * power_wkg

    Attributes:
        power_a: Intercept coefficient (baseline speed)
        power_b: Slope coefficient (speed gain per W/kg)
        power_rmse: Root Mean Square Error of the model
    """

    def __init__(self):
        """Initialize empty model."""
        self.power_a: float = 0.0
        self.power_b: float = 0.0
        self.power_rmse: float = 0.0

    def fit(self, power_wkg_values: list[float], speeds: list[float]) -> None:
        """Fit linear regression model.

        Args:
            power_wkg_values: Power per kg (W/kg) values
            speeds: Speed values (m/s)

        Raises:
            ValueError: If insufficient data or zero variance
        """
        if len(power_wkg_values) < 2 or len(speeds) < 2:
            raise ValueError("Need at least 2 data points for linear regression")

        if len(power_wkg_values) != len(speeds):
            raise ValueError("power_wkg_values and speeds must have same length")

        x = np.array(power_wkg_values)
        y = np.array(speeds)

        # Check for zero variance
        if np.std(x) == 0:
            raise ValueError(
                "power_wkg_values has zero variance (all values are the same)"
            )

        # Perform linear regression
        result = stats.linregress(x, y)

        self.power_b = float(result.slope)
        self.power_a = float(result.intercept)

        # Calculate RMSE
        y_pred = self.power_a + self.power_b * x
        self.power_rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))

    def predict(self, power_wkg: float) -> float:
        """Predict speed from power per kg.

        Args:
            power_wkg: Power per kg (W/kg)

        Returns:
            Predicted speed (m/s)
        """
        return self.power_a + self.power_b * power_wkg
