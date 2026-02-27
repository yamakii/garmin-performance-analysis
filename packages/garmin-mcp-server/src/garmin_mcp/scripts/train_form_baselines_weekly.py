#!/usr/bin/env python3
"""Train form baseline models for specific date using 2-month rolling window.

This script trains statistical models (GCT power law, VO/VR linear models)
using a 2-month rolling window ending on the specified date, and stores
the results in form_baseline_history table for trend analysis.

Usage:
    # Train on data ending on 2025-10-06 (2-month window: 2025-08-07 to 2025-10-06)
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly.py --end-date 2025-10-06

    # Train for all October 2025 Mondays
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly.py --end-date 2025-10-06
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly.py --end-date 2025-10-13
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly.py --end-date 2025-10-20
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly.py --end-date 2025-10-27
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.form_baseline import trainer, utils
from garmin_mcp.form_baseline.trainer import GCTPowerModel, LinearModel


def parse_date(date_str: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM-DD string and calculate 2-month rolling window.

    Args:
        date_str: End date string (e.g., "2025-10-06")

    Returns:
        Tuple of (period_start, period_end) as datetime objects

    Example:
        >>> parse_date("2025-10-06")
        (datetime(2025, 8, 7), datetime(2025, 10, 6))
    """
    try:
        # Parse end date
        period_end = datetime.strptime(date_str, "%Y-%m-%d")

        # Calculate period_start: 2 months before (60 days)
        period_start = period_end - relativedelta(months=2) + relativedelta(days=1)

        return period_start, period_end

    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Expected YYYY-MM-DD (e.g., 2025-10-06)"
        ) from e


def main() -> int:
    """Main entry point for weekly training."""
    parser = argparse.ArgumentParser(
        description="Train form baseline models using 2-month rolling window ending on specified date"
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date in YYYY-MM-DD format (e.g., 2025-10-06)",
    )
    parser.add_argument(
        "--condition",
        default="flat_road",
        help="Condition group name (default: flat_road)",
    )
    parser.add_argument(
        "--db-path",
        default="data/database/garmin_performance.duckdb",
        help="Path to DuckDB database (default: data/database/garmin_performance.duckdb)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=50,
        help="Minimum number of samples required (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Parse end date and calculate 2-month window
    try:
        period_start, period_end = parse_date(args.end_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(
            f"Training period: {period_start.date()} to {period_end.date()} (2 months)",
            file=sys.stderr,
        )

    # Validate database path
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    # Connect to DuckDB and fetch data for the 2-month window
    with get_write_connection(db_path) as conn:
        try:
            # Query with date filter for 2-month window (2021 and 2025 data only)
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
                  AND (EXTRACT(YEAR FROM a.activity_date) = 2021 OR EXTRACT(YEAR FROM a.activity_date) = 2025)
            """

            df = conn.execute(query).df()

            if args.verbose:
                print(
                    f"Loaded {len(df)} splits from {period_start.date()} to {period_end.date()}",
                    file=sys.stderr,
                )

        except Exception as e:
            print(f"Error loading data from database: {e}", file=sys.stderr)
            return 1

        # Check if we have enough data
        if len(df) < args.min_samples:
            print(
                f"Error: Insufficient data ({len(df)} samples). Need at least {args.min_samples} samples.",
                file=sys.stderr,
            )
            return 1

        # Preprocess data
        if args.verbose:
            print("Preprocessing data (removing outliers)...", file=sys.stderr)

        df_clean = df.copy()
        df_clean = utils.drop_outliers(df_clean, "ground_contact_time", (150.0, 350.0))
        df_clean = utils.drop_outliers(df_clean, "vertical_oscillation", (5.0, 20.0))
        df_clean = utils.drop_outliers(df_clean, "vertical_ratio", (4.0, 15.0))

        if args.verbose:
            print(
                f"After outlier removal: {len(df_clean)} samples "
                f"({len(df) - len(df_clean)} removed)",
                file=sys.stderr,
            )

        # Check sample count after outlier removal
        if len(df_clean) < args.min_samples:
            print(
                f"Error: Insufficient data after outlier removal ({len(df_clean)} samples). "
                f"Need at least {args.min_samples} samples.",
                file=sys.stderr,
            )
            return 1

        # Add derived columns
        df_clean["speed_mps"] = df_clean["pace_seconds_per_km"].apply(utils.to_speed)
        df_clean["gct_ms"] = df_clean["ground_contact_time"]
        df_clean["vo_value"] = df_clean["vertical_oscillation"]
        df_clean["vr_value"] = df_clean["vertical_ratio"]

        # Train models
        if args.verbose:
            print("Training models...", file=sys.stderr)

        try:
            gct_model: GCTPowerModel = trainer.fit_gct_power(df_clean)
            vo_model: LinearModel = trainer.fit_linear(df_clean, "vo")
            vr_model: LinearModel = trainer.fit_linear(df_clean, "vr")
        except Exception as e:
            print(f"Error training models: {e}", file=sys.stderr)
            return 1

        # Save to form_baseline_history
        if args.verbose:
            print("Saving to form_baseline_history...", file=sys.stderr)

        try:
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
                    "default",
                    args.condition,
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
                    "default",
                    args.condition,
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
                    "default",
                    args.condition,
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

            if args.verbose:
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


if __name__ == "__main__":
    sys.exit(main())
