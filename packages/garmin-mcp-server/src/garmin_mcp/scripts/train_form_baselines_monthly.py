#!/usr/bin/env python3
"""Train form baseline models using a 2-month rolling window for a target month.

This script trains statistical models (GCT power law, VO/VR linear models)
using a 2-month rolling window (the target month plus the preceding month),
and stores the results in form_baseline_history table for trend analysis.

The shared training body lives in
``garmin_mcp.scripts._form_baseline_training``; this module only parses CLI
arguments and derives the window from ``--year-month``.

Usage:
    # Train on data from 2025-09-01 to 2025-10-31 (2-month window for Oct 2025)
    uv run python -m garmin_mcp.scripts.train_form_baselines_monthly --year-month 2025-10

    # Specify custom database path
    uv run python -m garmin_mcp.scripts.train_form_baselines_monthly --year-month 2025-10 \
        --db-path ~/garmin_data/data/database/garmin_performance.duckdb
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

from garmin_mcp.scripts._form_baseline_training import train_and_store_baseline


def parse_year_month(year_month_str: str) -> tuple[datetime, datetime]:
    """Parse YYYY-MM string and calculate 2-month rolling window.

    The window spans the target month plus the preceding month:
    ``period_start`` is the first day of the previous month and
    ``period_end`` is the last day of the target month.

    Args:
        year_month_str: Year-month string (e.g., "2025-10")

    Returns:
        Tuple of (period_start, period_end) as datetime objects

    Example:
        >>> parse_year_month("2025-10")
        (datetime(2025, 9, 1), datetime(2025, 10, 31))
    """
    try:
        # Parse target year-month
        target_date = datetime.strptime(year_month_str, "%Y-%m")

        # Calculate period_start: first day of the previous month
        period_start = target_date - relativedelta(months=1)

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
        description="Train form baseline models using 2-month rolling window"
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

    # Parse year-month and calculate 2-month window
    try:
        period_start, period_end = parse_year_month(args.year_month)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return train_and_store_baseline(
        period_start,
        period_end,
        condition=args.condition,
        db_path=Path(args.db_path),
        min_samples=args.min_samples,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
