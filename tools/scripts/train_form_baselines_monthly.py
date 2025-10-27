#!/usr/bin/env python3
"""Train form baseline models using 6-month rolling window.

This script trains statistical models (GCT power law, VO/VR linear models)
using a 6-month rolling window of data, and stores the results in
form_baseline_history table for trend analysis.

Usage:
    # Train on data from 2025-05-01 to 2025-10-31 (6 months ending in Oct 2025)
    uv run python tools/scripts/train_form_baselines_monthly.py --year-month 2025-10

    # Specify custom database path
    uv run python tools/scripts/train_form_baselines_monthly.py --year-month 2025-10 \
        --db-path ~/garmin_data/data/database/garmin_performance.duckdb
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import duckdb
from dateutil.relativedelta import relativedelta

from tools.form_baseline import trainer, utils
from tools.form_baseline.trainer import GCTPowerModel, LinearModel


def parse_year_month(year_month_str: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM string and calculate 6-month rolling window.

    Args:
        year_month_str: Year-month string (e.g., "2025-10")

    Returns:
        Tuple of (period_start, period_end) as datetime objects

    Example:
        >>> parse_year_month("2025-10")
        (datetime(2025, 5, 1), datetime(2025, 10, 31))
    """
    try:
        # Parse target year-month
        target_date = datetime.strptime(year_month_str, "%Y-%m")

        # Calculate period_start: 6 months before target month
        period_start = target_date - relativedelta(months=5)

        # Calculate period_end: last day of target month
        if target_date.month == 12:
            period_end = datetime(target_date.year, 12, 31)
        else:
            next_month = target_date + relativedelta(months=1)
            period_end = next_month - relativedelta(days=1)

        return period_start, period_end

    except ValueError as e:
        raise ValueError(
            f"Invalid year-month format: {year_month_str}. Expected YYYY-MM (e.g., 2025-10)"
        ) from e


def main() -> int:
    """Main entry point for monthly training."""
    parser = argparse.ArgumentParser(
        description="Train form baseline models using 6-month rolling window"
    )
    parser.add_argument(
        "--year-month",
        required=True,
        help="Target year-month in YYYY-MM format (e.g., 2025-10)",
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

    # Parse year-month and calculate 6-month window
    try:
        period_start, period_end = parse_year_month(args.year_month)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.verbose:
        print(
            f"Training period: {period_start.date()} to {period_end.date()} (6 months)",
            file=sys.stderr,
        )

    # Validate database path
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    # Connect to DuckDB and fetch data for the 6-month window
    try:
        conn = duckdb.connect(str(db_path), read_only=False)

        # Query with date filter for 6-month window
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
        """

        df = conn.execute(query).df()

        if args.verbose:
            print(
                f"Loaded {len(df)} splits from {period_start.date()} to {period_end.date()}",
                file=sys.stderr,
            )

    except Exception as e:
        print(f"Error loading data from database: {e}", file=sys.stderr)
        conn.close()
        return 1

    # Check if we have enough data
    if len(df) < args.min_samples:
        print(
            f"Error: Insufficient data ({len(df)} samples). Need at least {args.min_samples} samples.",
            file=sys.stderr,
        )
        conn.close()
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
        conn.close()
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
        conn.close()
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

        conn.close()

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
        conn.close()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
