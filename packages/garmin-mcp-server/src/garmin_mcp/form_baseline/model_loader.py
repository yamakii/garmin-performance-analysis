"""Model loading utilities for form baseline evaluation.

Handles loading trained models from JSON files and DuckDB.
"""

import json
from pathlib import Path

import duckdb

from .trainer import GCTPowerModel, LinearModel


def load_models_from_file(
    model_file: Path,
) -> dict[str, GCTPowerModel | LinearModel]:
    """Load trained models from JSON file.

    Args:
        model_file: Path to JSON file with model coefficients

    Returns:
        Dictionary of models: {'gct': GCTPowerModel, 'vo': LinearModel, 'vr': LinearModel}

    Raises:
        FileNotFoundError: If model file doesn't exist
        ValueError: If JSON format is invalid
    """
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")

    with open(model_file) as f:
        data = json.load(f)

    # Create GCT power model
    gct_data = data["gct"]
    gct_model = GCTPowerModel(
        alpha=gct_data["alpha"],
        d=gct_data["d"],
        rmse=gct_data["rmse"],
        n_samples=gct_data["n_samples"],
        speed_range=(gct_data["speed_range"]["min"], gct_data["speed_range"]["max"]),
    )

    # Create VO linear model
    vo_data = data["vo"]
    vo_model = LinearModel(
        a=vo_data["a"],
        b=vo_data["b"],
        rmse=vo_data["rmse"],
        n_samples=vo_data["n_samples"],
        speed_range=(vo_data["speed_range"]["min"], vo_data["speed_range"]["max"]),
    )

    # Create VR linear model
    vr_data = data["vr"]
    vr_model = LinearModel(
        a=vr_data["a"],
        b=vr_data["b"],
        rmse=vr_data["rmse"],
        n_samples=vr_data["n_samples"],
        speed_range=(vr_data["speed_range"]["min"], vr_data["speed_range"]["max"]),
    )

    return {
        "gct": gct_model,
        "vo": vo_model,
        "vr": vr_model,
    }


def load_models_from_db(
    db_path: str,
    activity_date: str,
    user_id: str = "default",
    condition_group: str = "flat_road",
) -> dict[str, GCTPowerModel | LinearModel]:
    """Load trained models from DuckDB form_baseline_history.

    Selects the baseline period that covers the activity_date
    (where period_end <= activity_date).

    Args:
        db_path: Path to DuckDB database
        activity_date: Activity date in YYYY-MM-DD format
        user_id: User identifier (default: 'default')
        condition_group: Condition group name (default: 'flat_road')

    Returns:
        Dictionary of models: {'gct': GCTPowerModel, 'vo': LinearModel, 'vr': LinearModel}

    Raises:
        ValueError: If no baseline found for the activity date
    """
    conn = duckdb.connect(db_path, read_only=True)

    try:
        baselines = conn.execute(
            """
            WITH latest_baseline AS (
                SELECT MAX(period_end) as max_period_end
                FROM form_baseline_history
                WHERE user_id = ?
                  AND condition_group = ?
                  AND period_end <= ?
            )
            SELECT metric, coef_alpha, coef_d, coef_a, coef_b,
                   n_samples, rmse, speed_range_min, speed_range_max
            FROM form_baseline_history
            WHERE user_id = ?
              AND condition_group = ?
              AND period_end = (SELECT max_period_end FROM latest_baseline)
            """,
            [user_id, condition_group, activity_date, user_id, condition_group],
        ).fetchall()

        if not baselines:
            raise ValueError(
                f"No baseline found for activity_date={activity_date}, "
                f"user_id={user_id}, condition_group={condition_group}. "
                f"Train a baseline model with period_end <= {activity_date}"
            )

        # Parse baselines by metric
        models: dict[str, GCTPowerModel | LinearModel] = {}
        for row in baselines:
            metric, alpha, d, a, b, n_samples, rmse, speed_min, speed_max = row

            if metric == "gct":
                models["gct"] = GCTPowerModel(
                    alpha=float(alpha),
                    d=float(d),
                    rmse=float(rmse),
                    n_samples=int(n_samples),
                    speed_range=(float(speed_min), float(speed_max)),
                )
            elif metric == "vo":
                models["vo"] = LinearModel(
                    a=float(a),
                    b=float(b),
                    rmse=float(rmse),
                    n_samples=int(n_samples),
                    speed_range=(float(speed_min), float(speed_max)),
                )
            elif metric == "vr":
                models["vr"] = LinearModel(
                    a=float(a),
                    b=float(b),
                    rmse=float(rmse),
                    n_samples=int(n_samples),
                    speed_range=(float(speed_min), float(speed_max)),
                )

        # Validate all metrics present
        if len(models) != 3 or not all(m in models for m in ["gct", "vo", "vr"]):
            raise ValueError(
                f"Incomplete baseline data. Found metrics: {list(models.keys())}"
            )

        return models

    finally:
        conn.close()
