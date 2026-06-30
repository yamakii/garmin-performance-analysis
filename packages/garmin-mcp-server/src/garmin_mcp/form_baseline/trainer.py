"""Statistical model training for form baseline system."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, RANSACRegressor

from garmin_mcp.form_baseline.utils import drop_outliers


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


def fit_linear(df: pd.DataFrame, metric: Literal["vo", "vr", "cadence"]) -> LinearModel:
    """
    Train linear model for VO, VR or cadence.

    Args:
        df: DataFrame with columns ['{metric}_value', 'speed_mps']
        metric: 'vo' (Vertical Oscillation), 'vr' (Vertical Ratio) or
            'cadence' (Step cadence). For cadence, b > 0 is expected
            (faster speed -> higher cadence), but no monotonicity check
            is enforced (linear fit only).

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
    elif metric == "cadence":
        df_clean = drop_outliers(df, column=column, valid_range=(140.0, 210.0))
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


def train_power_efficiency_baseline(
    user_id: str = "default",
    condition_group: str = "flat_road",
    end_date: str | None = None,
    window_months: int = 2,
    db_path: str | None = None,
) -> dict | None:
    """Train power efficiency baseline model.

    Model: speed_mps = power_a + power_b * power_wkg

    Args:
        user_id: User identifier
        condition_group: Condition group (e.g., 'flat_road')
        end_date: End date (YYYY-MM-DD). If None, uses today
        window_months: Training window in months (default: 2)
        db_path: Database path. If None, uses GARMIN_DATA_DIR

    Returns:
        Dict with trained model or None if insufficient data
        {
            'power_a': float,
            'power_b': float,
            'power_rmse': float,
            'n_samples': int,
            'period_start': str,
            'period_end': str,
        }

    Raises:
        None - Returns None on errors instead of raising
    """
    from datetime import datetime, timedelta

    from garmin_mcp.form_baseline.power_efficiency_model import PowerEfficiencyModel

    # Get database path
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    # Parse end_date
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    start_dt = end_dt - timedelta(days=window_months * 30)
    period_start = start_dt.strftime("%Y-%m-%d")
    period_end = end_dt.strftime("%Y-%m-%d")

    # Connect to database
    from garmin_mcp.database.connection import get_write_connection

    try:
        with get_write_connection(db_path) as conn:
            # Query data
            query = """
                SELECT
                    s.grade_adjusted_speed AS speed_mps,
                    s.power AS power_w,
                    a.base_weight_kg
                FROM splits s
                JOIN activities a ON s.activity_id = a.activity_id
                WHERE a.activity_date >= ?
                  AND a.activity_date <= ?
                  AND s.power IS NOT NULL
                  AND a.base_weight_kg IS NOT NULL
                  AND s.grade_adjusted_speed IS NOT NULL
                  AND s.role_phase = 'run'
                  AND s.grade_adjusted_speed > 1.5
                  AND s.grade_adjusted_speed < 7.0
            """

            result = conn.execute(query, [period_start, period_end]).fetchall()

            if len(result) < 10:
                # Insufficient data
                return None

            # Convert to power_wkg and speeds
            power_wkg_values = []
            speeds = []

            for row in result:
                speed_mps, power_w, base_weight_kg = row
                if power_w is None or base_weight_kg is None or base_weight_kg <= 0:
                    continue
                power_wkg = power_w / base_weight_kg
                power_wkg_values.append(power_wkg)
                speeds.append(speed_mps)

            if len(power_wkg_values) < 10:
                # Insufficient valid data
                return None

            # Fit model
            model = PowerEfficiencyModel()
            model.fit(power_wkg_values, speeds)

            # Insert into form_baseline_history with UPSERT
            conn.execute(
                """
                INSERT INTO form_baseline_history (
                    history_id,
                    user_id,
                    condition_group,
                    metric,
                    model_type,
                    period_start,
                    period_end,
                    n_samples,
                    power_a,
                    power_b,
                    power_rmse
                ) VALUES (nextval('form_baseline_history_seq'), ?, ?, 'power', 'linear', ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, condition_group, metric, period_start, period_end)
                DO UPDATE SET
                    model_type = EXCLUDED.model_type,
                    n_samples = EXCLUDED.n_samples,
                    power_a = EXCLUDED.power_a,
                    power_b = EXCLUDED.power_b,
                    power_rmse = EXCLUDED.power_rmse
                """,
                [
                    user_id,
                    condition_group,
                    period_start,
                    period_end,
                    len(power_wkg_values),
                    model.power_a,
                    model.power_b,
                    model.power_rmse,
                ],
            )

            return {
                "power_a": model.power_a,
                "power_b": model.power_b,
                "power_rmse": model.power_rmse,
                "n_samples": len(power_wkg_values),
                "period_start": period_start,
                "period_end": period_end,
            }

    except Exception as e:
        # Return None on any error (graceful degradation)
        import traceback

        print(f"Error in train_power_efficiency_baseline: {e}")
        traceback.print_exc()
        return None


def train_form_baselines(
    user_id: str = "default",
    condition_group: str = "flat_road",
    end_date: str | None = None,
    window_months: int = 2,
    db_path: str | None = None,
    min_samples: int = 50,
) -> dict[str, Any] | None:
    """Train all form baselines (GCT, VO, VR, cadence, Power) with rolling window.

    This is the single source of truth for batch form-baseline training. The
    ``train_form_baselines_weekly`` / ``train_form_baselines_monthly`` CLIs
    delegate here via ``_form_baseline_training.train_and_store_baseline``.

    GCT/VO/VR/cadence are always trained together from the same cleaned window.
    Power is best-effort: it depends on ``role_phase = 'run'`` splits with a
    non-null ``base_weight_kg``, so it can be legitimately absent for older
    periods that lack those columns (this is not treated as a failure).

    Args:
        user_id: User identifier
        condition_group: Condition group (e.g., 'flat_road')
        end_date: End date (YYYY-MM-DD). If None, uses today
        window_months: Training window in months (default: 2)
        db_path: Database path. If None, uses GARMIN_DATA_DIR
        min_samples: Minimum number of samples required, both before and after
            outlier removal (default: 50). Below this the window is skipped and
            None is returned.

    Returns:
        Dict with trained models or None if insufficient data
        {
            'gct': {'alpha': float, 'd': float, 'rmse': float, 'n_samples': int},
            'vo': {'a': float, 'b': float, 'rmse': float, 'n_samples': int},
            'vr': {'a': float, 'b': float, 'rmse': float, 'n_samples': int},
            'cadence': {'a': float, 'b': float, 'rmse': float, 'n_samples': int},
            'power': {'power_a': float, 'power_b': float, 'power_rmse': float, 'n_samples': int},
            'period_start': str,
            'period_end': str,
        }

    Raises:
        None - Returns None on errors instead of raising
    """
    from dateutil.relativedelta import relativedelta

    from garmin_mcp.form_baseline import utils

    # Get database path
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    # Parse end_date
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Calculate period_start: 2 months before (60 days)
    start_dt = end_dt - relativedelta(months=window_months) + relativedelta(days=1)
    period_start = start_dt.strftime("%Y-%m-%d")
    period_end = end_dt.strftime("%Y-%m-%d")

    # Connect to database
    from garmin_mcp.database.connection import get_write_connection

    try:
        with get_write_connection(db_path) as conn:
            # Query with date filter for 2-month window
            query = """
            SELECT
                s.pace_seconds_per_km,
                s.ground_contact_time,
                s.vertical_oscillation,
                s.vertical_ratio,
                s.stride_length,
                s.cadence
            FROM splits s
            JOIN activities a ON s.activity_id = a.activity_id
            WHERE s.ground_contact_time IS NOT NULL
              AND s.vertical_oscillation IS NOT NULL
              AND s.vertical_ratio IS NOT NULL
              AND s.pace_seconds_per_km > 0
              AND s.pace_seconds_per_km < 600
              AND a.activity_date >= ?
              AND a.activity_date <= ?
        """

            df = conn.execute(query, [period_start, period_end]).df()

            if len(df) < min_samples:
                # Insufficient data
                return None

            # Preprocess data
            df_clean = df.copy()
            df_clean = utils.drop_outliers(
                df_clean, "ground_contact_time", (150.0, 350.0)
            )
            df_clean = utils.drop_outliers(
                df_clean, "vertical_oscillation", (5.0, 20.0)
            )
            df_clean = utils.drop_outliers(df_clean, "vertical_ratio", (4.0, 15.0))
            df_clean = utils.drop_outliers(df_clean, "cadence", (140.0, 210.0))

            if len(df_clean) < min_samples:
                # Insufficient data after outlier removal
                return None

            # Add derived columns
            df_clean["speed_mps"] = df_clean["pace_seconds_per_km"].apply(
                utils.to_speed
            )
            df_clean["gct_ms"] = df_clean["ground_contact_time"]
            df_clean["vo_value"] = df_clean["vertical_oscillation"]
            df_clean["vr_value"] = df_clean["vertical_ratio"]
            df_clean["cadence_value"] = df_clean["cadence"]

            # Train GCT, VO, VR, cadence models
            gct_model: GCTPowerModel = fit_gct_power(df_clean)
            vo_model: LinearModel = fit_linear(df_clean, "vo")
            vr_model: LinearModel = fit_linear(df_clean, "vr")
            cadence_model: LinearModel = fit_linear(df_clean, "cadence")

            # Insert GCT model
            conn.execute(
                """
            INSERT INTO form_baseline_history (
                history_id, user_id, condition_group, metric, model_type,
                coef_alpha, coef_d, coef_a, coef_b,
                period_start, period_end,
                n_samples, rmse, speed_range_min, speed_range_max
            ) VALUES (nextval('form_baseline_history_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, condition_group, metric, period_start, period_end)
            DO UPDATE SET
                model_type = EXCLUDED.model_type,
                coef_alpha = EXCLUDED.coef_alpha,
                coef_d = EXCLUDED.coef_d,
                coef_a = EXCLUDED.coef_a,
                coef_b = EXCLUDED.coef_b,
                n_samples = EXCLUDED.n_samples,
                rmse = EXCLUDED.rmse,
                speed_range_min = EXCLUDED.speed_range_min,
                speed_range_max = EXCLUDED.speed_range_max,
                trained_at = now()
            """,
                [
                    user_id,
                    condition_group,
                    "gct",
                    "power",
                    gct_model.alpha,
                    gct_model.d,
                    None,
                    None,
                    period_start,
                    period_end,
                    gct_model.n_samples,
                    gct_model.rmse,
                    gct_model.speed_range[0],
                    gct_model.speed_range[1],
                ],
            )

            # Insert VO model
            conn.execute(
                """
            INSERT INTO form_baseline_history (
                history_id, user_id, condition_group, metric, model_type,
                coef_alpha, coef_d, coef_a, coef_b,
                period_start, period_end,
                n_samples, rmse, speed_range_min, speed_range_max
            ) VALUES (nextval('form_baseline_history_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, condition_group, metric, period_start, period_end)
            DO UPDATE SET
                model_type = EXCLUDED.model_type,
                coef_alpha = EXCLUDED.coef_alpha,
                coef_d = EXCLUDED.coef_d,
                coef_a = EXCLUDED.coef_a,
                coef_b = EXCLUDED.coef_b,
                n_samples = EXCLUDED.n_samples,
                rmse = EXCLUDED.rmse,
                speed_range_min = EXCLUDED.speed_range_min,
                speed_range_max = EXCLUDED.speed_range_max,
                trained_at = now()
            """,
                [
                    user_id,
                    condition_group,
                    "vo",
                    "linear",
                    None,
                    None,
                    vo_model.a,
                    vo_model.b,
                    period_start,
                    period_end,
                    vo_model.n_samples,
                    vo_model.rmse,
                    vo_model.speed_range[0],
                    vo_model.speed_range[1],
                ],
            )

            # Insert VR model
            conn.execute(
                """
            INSERT INTO form_baseline_history (
                history_id, user_id, condition_group, metric, model_type,
                coef_alpha, coef_d, coef_a, coef_b,
                period_start, period_end,
                n_samples, rmse, speed_range_min, speed_range_max
            ) VALUES (nextval('form_baseline_history_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, condition_group, metric, period_start, period_end)
            DO UPDATE SET
                model_type = EXCLUDED.model_type,
                coef_alpha = EXCLUDED.coef_alpha,
                coef_d = EXCLUDED.coef_d,
                coef_a = EXCLUDED.coef_a,
                coef_b = EXCLUDED.coef_b,
                n_samples = EXCLUDED.n_samples,
                rmse = EXCLUDED.rmse,
                speed_range_min = EXCLUDED.speed_range_min,
                speed_range_max = EXCLUDED.speed_range_max,
                trained_at = now()
            """,
                [
                    user_id,
                    condition_group,
                    "vr",
                    "linear",
                    None,
                    None,
                    vr_model.a,
                    vr_model.b,
                    period_start,
                    period_end,
                    vr_model.n_samples,
                    vr_model.rmse,
                    vr_model.speed_range[0],
                    vr_model.speed_range[1],
                ],
            )

            # Insert cadence model
            conn.execute(
                """
            INSERT INTO form_baseline_history (
                history_id, user_id, condition_group, metric, model_type,
                coef_alpha, coef_d, coef_a, coef_b,
                period_start, period_end,
                n_samples, rmse, speed_range_min, speed_range_max
            ) VALUES (nextval('form_baseline_history_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, condition_group, metric, period_start, period_end)
            DO UPDATE SET
                model_type = EXCLUDED.model_type,
                coef_alpha = EXCLUDED.coef_alpha,
                coef_d = EXCLUDED.coef_d,
                coef_a = EXCLUDED.coef_a,
                coef_b = EXCLUDED.coef_b,
                n_samples = EXCLUDED.n_samples,
                rmse = EXCLUDED.rmse,
                speed_range_min = EXCLUDED.speed_range_min,
                speed_range_max = EXCLUDED.speed_range_max,
                trained_at = now()
            """,
                [
                    user_id,
                    condition_group,
                    "cadence",
                    "linear",
                    None,
                    None,
                    cadence_model.a,
                    cadence_model.b,
                    period_start,
                    period_end,
                    cadence_model.n_samples,
                    cadence_model.rmse,
                    cadence_model.speed_range[0],
                    cadence_model.speed_range[1],
                ],
            )

            # Train Power model
            power_result = train_power_efficiency_baseline(
                user_id=user_id,
                condition_group=condition_group,
                end_date=period_end,
                window_months=window_months,
                db_path=db_path,
            )

            result = {
                "gct": {
                    "alpha": gct_model.alpha,
                    "d": gct_model.d,
                    "rmse": gct_model.rmse,
                    "n_samples": gct_model.n_samples,
                },
                "vo": {
                    "a": vo_model.a,
                    "b": vo_model.b,
                    "rmse": vo_model.rmse,
                    "n_samples": vo_model.n_samples,
                },
                "vr": {
                    "a": vr_model.a,
                    "b": vr_model.b,
                    "rmse": vr_model.rmse,
                    "n_samples": vr_model.n_samples,
                },
                "cadence": {
                    "a": cadence_model.a,
                    "b": cadence_model.b,
                    "rmse": cadence_model.rmse,
                    "n_samples": cadence_model.n_samples,
                },
                "period_start": period_start,
                "period_end": period_end,
            }

            if power_result:
                result["power"] = {
                    "power_a": power_result["power_a"],
                    "power_b": power_result["power_b"],
                    "power_rmse": power_result["power_rmse"],
                    "n_samples": power_result["n_samples"],
                }

            return result

    except Exception as e:
        # Return None on any error (graceful degradation)
        import traceback

        print(f"Error in train_form_baselines: {e}")
        traceback.print_exc()
        return None


def _month_end(d: date) -> date:
    """Return the last day of the month containing ``d`` (handles December)."""
    import calendar

    last_day = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def _target_month_ends(activity_date: str) -> list[str]:
    """Return ``[current_month_end, prior_month_end]`` as "YYYY-MM-DD" strings.

    The current-month end matches the period_end used by the monthly baseline
    script (so periods align). The prior-month end is the day before the
    current month's first day.
    """
    d = datetime.strptime(activity_date, "%Y-%m-%d").date()
    current_end = _month_end(d)
    prior_end = date(d.year, d.month, 1) - timedelta(days=1)
    return [current_end.strftime("%Y-%m-%d"), prior_end.strftime("%Y-%m-%d")]


def ensure_form_baselines_for_date(
    activity_date: str,
    db_path: str | None = None,
    user_id: str = "default",
    condition_group: str = "flat_road",
) -> dict[str, list[str]]:
    """Generate the form baseline for an activity's month + prior month if missing.

    Self-healing helper invoked from prefetch so that form-trend comparison is
    always available. Never raises: any error is swallowed and reflected in the
    returned buckets. Each period is processed sequentially (single-writer).

    Args:
        activity_date: Activity date ("YYYY-MM-DD"). Determines target months.
        db_path: Database path. If None, uses GARMIN_DATA_DIR resolution.
        user_id: User identifier.
        condition_group: Condition group (e.g., 'flat_road').

    Returns:
        Dict with three buckets keyed by period_end ("YYYY-MM-DD"):
        ``{"generated": [...], "skipped": [...], "insufficient": [...]}``.
    """
    from garmin_mcp.database.connection import get_connection

    result: dict[str, list[str]] = {
        "generated": [],
        "skipped": [],
        "insufficient": [],
    }

    try:
        period_ends = _target_month_ends(activity_date)
    except Exception:
        return result

    for period_end in period_ends:
        # Existence check (read connection closed before any write).
        # All four form metrics (gct/vo/vr/cadence) must be present; a period
        # with only some metrics (e.g. gct created by an older batch run that
        # predated cadence support) is treated as incomplete and re-trained.
        # power is best-effort and intentionally excluded to avoid re-training
        # loops on periods where it is legitimately absent (#640).
        try:
            with get_connection(db_path) as conn:
                count_row = conn.execute(
                    """
                    SELECT COUNT(DISTINCT metric)
                    FROM form_baseline_history
                    WHERE period_end = ?
                      AND metric IN ('gct', 'vo', 'vr', 'cadence')
                      AND user_id = ?
                      AND condition_group = ?
                    """,
                    [period_end, user_id, condition_group],
                ).fetchone()
            exists = count_row is not None and count_row[0] == 4
        except Exception:
            # If the existence check fails, skip this period defensively.
            continue

        if exists:
            result["skipped"].append(period_end)
            continue

        # Missing -> train (train_form_baselines opens its own write connection).
        try:
            trained = train_form_baselines(
                user_id=user_id,
                condition_group=condition_group,
                end_date=period_end,
                window_months=2,
                db_path=db_path,
            )
        except Exception:
            trained = None

        if trained is None:
            result["insufficient"].append(period_end)
        else:
            result["generated"].append(period_end)

    return result
