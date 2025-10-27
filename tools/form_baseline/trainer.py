"""Statistical model training for form baseline system."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, RANSACRegressor

from tools.form_baseline.utils import drop_outliers


@dataclass
class GCTPowerModel:
    """
    Power law model for GCT: v = c * (GCT)^d

    In log-log space: log(v) = alpha + d * log(GCT)
    where alpha = log(c) and d < 0 for monotonicity.
    """

    alpha: float  # log(c) - intercept in log-log space
    d: float  # slope in log-log space (should be < 0)
    rmse: float  # Root Mean Squared Error
    n_samples: int  # Number of training samples
    speed_range: tuple[float, float]  # (min, max) speed in m/s

    def predict(self, gct_ms: float) -> float:
        """
        Predict speed from GCT (forward prediction).

        Args:
            gct_ms: Ground Contact Time in milliseconds

        Returns:
            Speed in m/s
        """
        return float(np.exp(self.alpha + self.d * np.log(gct_ms)))

    def predict_inverse(self, speed_mps: float) -> float:
        """
        Predict GCT from speed (inverse prediction - used for evaluation).

        Args:
            speed_mps: Speed in m/s

        Returns:
            Expected GCT in milliseconds
        """
        return float(np.exp((np.log(speed_mps) - self.alpha) / self.d))


@dataclass
class LinearModel:
    """
    Linear model for VO/VR: y = a + b * v

    Typically b <= 0 for running metrics.
    """

    a: float  # Intercept
    b: float  # Slope
    rmse: float  # Root Mean Squared Error
    n_samples: int  # Number of training samples
    speed_range: tuple[float, float]  # (min, max) speed in m/s

    def predict(self, speed_mps: float) -> float:
        """
        Predict metric value from speed.

        Args:
            speed_mps: Speed in m/s

        Returns:
            Predicted metric value (VO in cm, VR in %)
        """
        return self.a + self.b * speed_mps


def fit_gct_power(df: pd.DataFrame, fallback_ransac: bool = True) -> GCTPowerModel:
    """
    Train GCT power law model using robust regression.

    Args:
        df: DataFrame with columns ['gct_ms', 'speed_mps']
        fallback_ransac: Use RANSAC if Huber fails monotonicity check

    Returns:
        GCTPowerModel with d < 0 guaranteed

    Raises:
        ValueError: If monotonicity cannot be achieved
    """
    # Remove outliers
    df_clean = drop_outliers(df, column="gct_ms", valid_range=(100, 400))
    df_clean = drop_outliers(df_clean, column="speed_mps", valid_range=(1.5, 7.0))

    if len(df_clean) < 3:
        raise ValueError(
            f"Insufficient data after outlier removal: {len(df_clean)} samples"
        )

    # Log-log transformation
    x_log = np.log(df_clean["gct_ms"].values).reshape(-1, 1)
    y_log = np.log(df_clean["speed_mps"].values)

    # Try Huber regression first (robust to outliers)
    huber = HuberRegressor()
    huber.fit(x_log, y_log)
    alpha = huber.intercept_
    d = huber.coef_[0]

    # Check monotonicity (d < 0 expected: faster speed -> shorter GCT)
    if d >= 0:
        if not fallback_ransac:
            raise ValueError(f"Non-monotonic GCT model: d={d:.3f} >= 0")

        # Fallback to RANSAC
        ransac = RANSACRegressor(min_samples=max(3, int(0.8 * len(df_clean))))
        ransac.fit(x_log, y_log)
        alpha = ransac.estimator_.intercept_
        d = ransac.estimator_.coef_[0]

        if d >= 0:
            raise ValueError(f"RANSAC failed to find monotonic model: d={d:.3f} >= 0")

    # Calculate RMSE
    y_pred = alpha + d * x_log.flatten()
    rmse = np.sqrt(np.mean((y_log - y_pred) ** 2))

    return GCTPowerModel(
        alpha=float(alpha),
        d=float(d),
        rmse=float(rmse),
        n_samples=len(df_clean),
        speed_range=(
            float(df_clean["speed_mps"].min()),
            float(df_clean["speed_mps"].max()),
        ),
    )


def fit_linear(df: pd.DataFrame, metric: Literal["vo", "vr"]) -> LinearModel:
    """
    Train linear model for VO or VR.

    Args:
        df: DataFrame with columns ['{metric}_value', 'speed_mps']
        metric: 'vo' (Vertical Oscillation) or 'vr' (Vertical Ratio)

    Returns:
        LinearModel

    Raises:
        ValueError: If insufficient data
    """
    column = f"{metric}_value"

    # Remove outliers based on metric type
    if metric == "vo":
        df_clean = drop_outliers(df, column=column, valid_range=(2, 15))
    elif metric == "vr":
        df_clean = drop_outliers(df, column=column, valid_range=(2, 20))
    else:
        raise ValueError(f"Unknown metric: {metric}")

    df_clean = drop_outliers(df_clean, column="speed_mps", valid_range=(1.5, 7.0))

    if len(df_clean) < 2:
        raise ValueError(
            f"Insufficient data after outlier removal: {len(df_clean)} samples"
        )

    # Linear regression with Huber (robust)
    x_speed = df_clean["speed_mps"].values.reshape(-1, 1)
    y_metric = df_clean[column].values

    huber = HuberRegressor()
    huber.fit(x_speed, y_metric)
    a = huber.intercept_
    b = huber.coef_[0]

    # Calculate RMSE
    y_pred = huber.predict(x_speed)
    rmse = np.sqrt(np.mean((y_metric - y_pred) ** 2))

    return LinearModel(
        a=float(a),
        b=float(b),
        rmse=float(rmse),
        n_samples=len(df_clean),
        speed_range=(
            float(df_clean["speed_mps"].min()),
            float(df_clean["speed_mps"].max()),
        ),
    )
