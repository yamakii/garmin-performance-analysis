"""Model loading utilities for form baseline evaluation.

Handles loading trained models from JSON files and DuckDB.
"""

import json
from pathlib import Path

from garmin_mcp.database.connection import get_connection

from .trainer import GCTPowerModel, LinearModel


def load_models_from_file(
    model_file: Path,
) -> dict[str, GCTPowerModel | LinearModel]:
    """Load trained models from JSON file.

    Args:
        model_file: Path to JSON file with model coefficients

    Returns:
        Dictionary of models: {'gct': GCTPowerModel, 'vo': LinearModel,
        'vr': LinearModel}. May also contain 'cadence': LinearModel when a
        cadence baseline is available (optional for backward compatibility).

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

    models: dict[str, GCTPowerModel | LinearModel] = {
        "gct": gct_model,
        "vo": vo_model,
        "vr": vr_model,
    }

    # Cadence model is optional (backward compatible with older model files)
    cadence_data = data.get("cadence")
    if cadence_data is not None:
        models["cadence"] = LinearModel(
            a=cadence_data["a"],
            b=cadence_data["b"],
            rmse=cadence_data["rmse"],
            n_samples=cadence_data["n_samples"],
            speed_range=(
                cadence_data["speed_range"]["min"],
                cadence_data["speed_range"]["max"],
            ),
        )

    return models


def load_models_from_db(
    db_path: str,
    activity_date: str,
    user_id: str = "default",
    condition_group: str = "flat_road",
) -> dict[str, GCTPowerModel | LinearModel]:
    """Load trained models from DuckDB form_baseline_history.

    Selects the baseline period that *covers* the activity date
    (``period_start <= activity_date <= period_end``), preferring the most
    recently started one, and falls back to the newest period that already
    ended (``period_end <= activity_date``) when nothing covers it.

    Covering periods must be preferred because ``period_end`` is the nominal
    end of the training window, not the cut-off of the data behind it:
    ``trainer.ensure_form_baselines_for_date`` deliberately trains a baseline
    whose ``period_end`` is the activity's own month end, and an
    ended-periods-only rule could never select it. Before #1088 that made a
    September run get graded by the July-August model -- i.e. midsummer
    easy-only data judging faster autumn running, worth about 5% of expected
    GCT. The trade-off is mild self-inclusion (the activity may be among the
    ~130-260 splits behind its own baseline), which is negligible at that
    sample size.

    Args:
        db_path: Path to DuckDB database
        activity_date: Activity date in YYYY-MM-DD format
        user_id: User identifier (default: 'default')
        condition_group: Condition group name (default: 'flat_road')

    Returns:
        Dictionary of models: {'gct': GCTPowerModel, 'vo': LinearModel,
        'vr': LinearModel}. May also contain 'cadence': LinearModel when a
        cadence baseline is available (optional for backward compatibility).

    Raises:
        ValueError: If no baseline found for the activity date
    """
    with get_connection(db_path) as conn:
        baselines = conn.execute(
            """
            WITH candidates AS (
                SELECT period_start, period_end,
                       -- 0 = the period covers the activity date, 1 = it ended
                       CASE WHEN period_end >= ? THEN 0 ELSE 1 END AS tier,
                       -- covering periods rank by the most recent training
                       -- window start, ended ones by the latest end (the
                       -- pre-#1088 rule)
                       CASE WHEN period_end >= ? THEN period_start
                            ELSE period_end END AS sort_key
                FROM form_baseline_history
                WHERE user_id = ?
                  AND condition_group = ?
                  AND period_start <= ?
                  -- The power-efficiency baseline is trained on its own window
                  -- (period_start can differ by a day) and is loaded elsewhere.
                  -- Letting it compete here made it win the covering sort and
                  -- return a row set with no form metrics at all (#1092).
                  AND metric IN ('gct', 'vo', 'vr', 'cadence')
            ),
            selected AS (
                SELECT period_start, period_end
                FROM candidates
                -- (tier, sort_key, period_end, period_start) identifies exactly
                -- one window, so the pick is deterministic even when two
                -- windows share a period_end.
                ORDER BY tier, sort_key DESC, period_end DESC, period_start DESC
                LIMIT 1
            )
            SELECT f.metric, f.model_type, f.coef_alpha, f.coef_d,
                   f.coef_a, f.coef_b, f.n_samples, f.rmse,
                   f.speed_range_min, f.speed_range_max
            FROM form_baseline_history f
            -- JOIN, not two scalar subqueries: with ties in the ordering above
            -- those could resolve to different rows and yield an impossible
            -- (period_start, period_end) pair, matching nothing (#1092).
            JOIN selected s
              ON f.period_start = s.period_start
             AND f.period_end = s.period_end
            WHERE f.user_id = ?
              AND f.condition_group = ?
            """,
            [
                activity_date,
                activity_date,
                user_id,
                condition_group,
                activity_date,
                user_id,
                condition_group,
            ],
        ).fetchall()

        if not baselines:
            raise ValueError(
                f"No baseline found for activity_date={activity_date}, "
                f"user_id={user_id}, condition_group={condition_group}. "
                f"Train a baseline model with period_start <= {activity_date}"
            )

        # Parse baselines by metric
        models: dict[str, GCTPowerModel | LinearModel] = {}
        for row in baselines:
            (
                metric,
                model_type,
                alpha,
                d,
                a,
                b,
                n_samples,
                rmse,
                speed_min,
                speed_max,
            ) = row

            # 'linear_flat' marks a slope-suppressed (intercept-only) model
            # persisted by the trainer (#873). Older rows have NULL/'linear'.
            degenerate = model_type == "linear_flat"

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
                    degenerate=degenerate,
                )
            elif metric == "vr":
                models["vr"] = LinearModel(
                    a=float(a),
                    b=float(b),
                    rmse=float(rmse),
                    n_samples=int(n_samples),
                    speed_range=(float(speed_min), float(speed_max)),
                    degenerate=degenerate,
                )
            elif metric == "cadence":
                # Cadence is optional (backward compatible: absent in old DBs)
                models["cadence"] = LinearModel(
                    a=float(a),
                    b=float(b),
                    rmse=float(rmse),
                    n_samples=int(n_samples),
                    speed_range=(float(speed_min), float(speed_max)),
                    degenerate=degenerate,
                )

        # Validate core metrics present (cadence is optional)
        if not all(m in models for m in ["gct", "vo", "vr"]):
            raise ValueError(
                f"Incomplete baseline data. Found metrics: {list(models.keys())}"
            )

        return models
