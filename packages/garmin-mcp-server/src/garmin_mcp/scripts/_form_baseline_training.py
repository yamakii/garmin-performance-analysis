#!/usr/bin/env python3
"""Shared body for form baseline training scripts.

Both ``train_form_baselines_weekly`` and ``train_form_baselines_monthly`` reuse
this module. They differ only in how the (period_start, period_end) window is
derived from CLI arguments; everything else (data loading, outlier removal,
model fitting, and persistence to ``form_baseline_history``) is identical and
lives here.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.form_baseline import trainer, utils
from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel

# Single source of truth for the INSERT used by every metric.
_INSERT_SQL = """
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
"""


def train_and_store_baseline(
    period_start: datetime,
    period_end: datetime,
    *,
    condition: str,
    db_path: Path,
    min_samples: int = 50,
    verbose: bool = False,
) -> int:
    """Train GCT/VO/VR baseline models for a window and persist them.

    Args:
        period_start: Inclusive start of the rolling window.
        period_end: Inclusive end of the rolling window.
        condition: Condition group name (e.g., "flat_road").
        db_path: Path to the DuckDB database.
        min_samples: Minimum number of samples required (before and after
            outlier removal).
        verbose: Enable verbose logging to stderr.

    Returns:
        Process exit code (0 on success, 1 on failure).
    """
    if verbose:
        print(
            f"Training period: {period_start.date()} to {period_end.date()} (2 months)",
            file=sys.stderr,
        )

    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    with get_write_connection(db_path) as conn:
        try:
            # Query with date filter for the rolling window (2021 and 2025+ data)
            query = f"""
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
                  AND a.activity_date >= '{period_start.date()}'
                  AND a.activity_date <= '{period_end.date()}'
                  AND (EXTRACT(YEAR FROM a.activity_date) = 2021 OR EXTRACT(YEAR FROM a.activity_date) >= 2025)
            """

            df = conn.execute(query).df()

            if verbose:
                print(
                    f"Loaded {len(df)} splits from {period_start.date()} to {period_end.date()}",
                    file=sys.stderr,
                )

        except Exception as e:
            print(f"Error loading data from database: {e}", file=sys.stderr)
            return 1

        # Check if we have enough data
        if len(df) < min_samples:
            print(
                f"Error: Insufficient data ({len(df)} samples). Need at least {min_samples} samples.",
                file=sys.stderr,
            )
            return 1

        # Preprocess data
        if verbose:
            print("Preprocessing data (removing outliers)...", file=sys.stderr)

        df_clean = df.copy()
        df_clean = utils.drop_outliers(df_clean, "ground_contact_time", (150.0, 350.0))
        df_clean = utils.drop_outliers(df_clean, "vertical_oscillation", (5.0, 20.0))
        df_clean = utils.drop_outliers(df_clean, "vertical_ratio", (4.0, 15.0))

        if verbose:
            print(
                f"After outlier removal: {len(df_clean)} samples "
                f"({len(df) - len(df_clean)} removed)",
                file=sys.stderr,
            )

        # Check sample count after outlier removal
        if len(df_clean) < min_samples:
            print(
                f"Error: Insufficient data after outlier removal ({len(df_clean)} samples). "
                f"Need at least {min_samples} samples.",
                file=sys.stderr,
            )
            return 1

        # Add derived columns
        df_clean["speed_mps"] = df_clean["pace_seconds_per_km"].apply(utils.to_speed)
        df_clean["gct_ms"] = df_clean["ground_contact_time"]
        df_clean["vo_value"] = df_clean["vertical_oscillation"]
        df_clean["vr_value"] = df_clean["vertical_ratio"]

        # Train models
        if verbose:
            print("Training models...", file=sys.stderr)

        try:
            gct_model: GCTPowerModel = trainer.fit_gct_power(df_clean)
            vo_model: LinearModel = trainer.fit_linear(df_clean, "vo")
            vr_model: LinearModel = trainer.fit_linear(df_clean, "vr")
        except Exception as e:
            print(f"Error training models: {e}", file=sys.stderr)
            return 1

        # Save to form_baseline_history
        if verbose:
            print("Saving to form_baseline_history...", file=sys.stderr)

        try:
            # Insert GCT model
            conn.execute(
                _INSERT_SQL,
                [
                    "default",
                    condition,
                    "gct",
                    "power",
                    gct_model.alpha,
                    gct_model.d,
                    None,
                    None,
                    period_start.date(),
                    period_end.date(),
                    gct_model.n_samples,
                    gct_model.rmse,
                    gct_model.speed_range[0],
                    gct_model.speed_range[1],
                ],
            )

            # Insert VO model
            conn.execute(
                _INSERT_SQL,
                [
                    "default",
                    condition,
                    "vo",
                    "linear",
                    None,
                    None,
                    vo_model.a,
                    vo_model.b,
                    period_start.date(),
                    period_end.date(),
                    vo_model.n_samples,
                    vo_model.rmse,
                    vo_model.speed_range[0],
                    vo_model.speed_range[1],
                ],
            )

            # Insert VR model
            conn.execute(
                _INSERT_SQL,
                [
                    "default",
                    condition,
                    "vr",
                    "linear",
                    None,
                    None,
                    vr_model.a,
                    vr_model.b,
                    period_start.date(),
                    period_end.date(),
                    vr_model.n_samples,
                    vr_model.rmse,
                    vr_model.speed_range[0],
                    vr_model.speed_range[1],
                ],
            )

            if verbose:
                print("✓ Training complete!", file=sys.stderr)
                print(
                    f"  Period: {period_start.date()} to {period_end.date()}",
                    file=sys.stderr,
                )
                print(
                    f"  GCT: n={gct_model.n_samples}, RMSE={gct_model.rmse:.2f}",
                    file=sys.stderr,
                )
                print(
                    f"  VO:  n={vo_model.n_samples}, RMSE={vo_model.rmse:.2f}",
                    file=sys.stderr,
                )
                print(
                    f"  VR:  n={vr_model.n_samples}, RMSE={vr_model.rmse:.2f}",
                    file=sys.stderr,
                )

        except Exception as e:
            print(f"Error saving to database: {e}", file=sys.stderr)
            return 1

    return 0
