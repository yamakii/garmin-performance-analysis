#!/usr/bin/env python3
"""Train form baseline models for a specific date using a 2-month rolling window.

This script trains statistical models (GCT power law, VO/VR linear models)
using a 2-month rolling window ending on the specified date, and stores
the results in form_baseline_history table for trend analysis.

The shared training body lives in
``garmin_mcp.scripts._form_baseline_training``; this module only parses CLI
arguments and derives the window from ``--end-date``.

Usage:
    # Train on data ending on 2025-10-06 (2-month window: 2025-08-07 to 2025-10-06)
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly --end-date 2025-10-06

    # Train for all October 2025 Mondays
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly --end-date 2025-10-06
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly --end-date 2025-10-13
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly --end-date 2025-10-20
    uv run python -m garmin_mcp.scripts.train_form_baselines_weekly --end-date 2025-10-27
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

from garmin_mcp.scripts._form_baseline_training import train_and_store_baseline


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
