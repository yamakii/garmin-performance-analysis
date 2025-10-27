#!/usr/bin/env python3
"""Backfill script for form_baseline_history.

This script trains form baseline models for all months in a specified date range
by calling train_form_baselines_monthly.py for each month.

Usage:
    uv run python tools/scripts/backfill_baseline_history.py --start-date 2023-01 --end-date 2025-10
    uv run python tools/scripts/backfill_baseline_history.py --start-date 2024-01  # Defaults to current month

Examples:
    # Backfill from 2023-01 to 2025-10
    uv run python tools/scripts/backfill_baseline_history.py --start-date 2023-01 --end-date 2025-10

    # Backfill from 2024-01 to now
    uv run python tools/scripts/backfill_baseline_history.py --start-date 2024-01

    # Dry run to see what would be executed
    uv run python tools/scripts/backfill_baseline_history.py --start-date 2023-01 --dry-run
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta


def parse_year_month(year_month_str: str) -> datetime:
    """Parse YYYY-MM string to datetime.

    Args:
        year_month_str: Year-month string in YYYY-MM format

    Returns:
        datetime object set to first day of the month

    Raises:
        ValueError: If format is invalid
    """
    try:
        return datetime.strptime(year_month_str, "%Y-%m")
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: {year_month_str}. Expected YYYY-MM format."
        ) from e


def generate_month_range(start_date: datetime, end_date: datetime) -> list[str]:
    """Generate list of YYYY-MM strings for all months in range.

    Args:
        start_date: Start month (inclusive)
        end_date: End month (inclusive)

    Returns:
        List of month strings in YYYY-MM format

    Example:
        >>> generate_month_range(datetime(2024, 10, 1), datetime(2024, 12, 1))
        ['2024-10', '2024-11', '2024-12']
    """
    months = []
    current = start_date

    while current <= end_date:
        months.append(current.strftime("%Y-%m"))
        current += relativedelta(months=1)

    return months


def train_month(
    year_month: str,
    db_path: str,
    condition_group: str,
    min_samples: int,
    verbose: bool,
    dry_run: bool,
) -> bool:
    """Train form baseline models for a single month.

    Args:
        year_month: Month in YYYY-MM format
        db_path: Path to DuckDB database
        condition_group: Condition group name
        min_samples: Minimum number of samples required
        verbose: Enable verbose output
        dry_run: If True, only print command without executing

    Returns:
        True if training succeeded, False otherwise
    """
    cmd = [
        "uv",
        "run",
        "python",
        "tools/scripts/train_form_baselines_monthly.py",
        "--year-month",
        year_month,
        "--db-path",
        db_path,
        "--condition",
        condition_group,
        "--min-samples",
        str(min_samples),
    ]

    if verbose:
        cmd.append("--verbose")

    if dry_run:
        print(f"[DRY RUN] Would execute: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )

        if verbose:
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

        return True

    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to train {year_month}:", file=sys.stderr)
        print(f"  {e.stderr}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill form baseline history for date range"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start month in YYYY-MM format",
    )
    parser.add_argument(
        "--end-date",
        help="End month in YYYY-MM format (default: current month)",
    )
    parser.add_argument(
        "--db-path",
        default="data/database/garmin_performance.duckdb",
        help="Path to DuckDB database (default: data/database/garmin_performance.duckdb)",
    )
    parser.add_argument(
        "--condition",
        default="flat_road",
        help="Condition group name (default: flat_road)",
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
        help="Enable verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing even if some months fail",
    )

    args = parser.parse_args()

    # Parse dates
    try:
        start_date = parse_year_month(args.start_date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.end_date:
        try:
            end_date = parse_year_month(args.end_date)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        # Default to current month
        end_date = datetime.now().replace(day=1)

    # Validate date range
    if start_date > end_date:
        print(
            f"Error: Start date ({args.start_date}) is after end date ({end_date.strftime('%Y-%m')})",
            file=sys.stderr,
        )
        return 1

    # Validate database path (unless dry run)
    if not args.dry_run:
        db_path = Path(args.db_path)
        if not db_path.exists():
            print(f"Error: Database not found: {db_path}", file=sys.stderr)
            return 1

    # Generate month range
    months = generate_month_range(start_date, end_date)

    print(
        f"Backfilling {len(months)} months: {args.start_date} to {end_date.strftime('%Y-%m')}"
    )
    if args.dry_run:
        print("[DRY RUN MODE - No actual training will occur]")
    print()

    # Train each month
    success_count = 0
    fail_count = 0

    for i, month in enumerate(months, 1):
        print(f"[{i}/{len(months)}] Training {month}...", end=" ", flush=True)

        success = train_month(
            year_month=month,
            db_path=args.db_path,
            condition_group=args.condition,
            min_samples=args.min_samples,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )

        if success:
            print("✓")
            success_count += 1
        else:
            print("✗")
            fail_count += 1
            if not args.continue_on_error:
                print(
                    "\nStopping due to error. Use --continue-on-error to continue.",
                    file=sys.stderr,
                )
                break

    # Summary
    print()
    print("=" * 50)
    print("Backfill Summary:")
    print(f"  Total months: {len(months)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {fail_count}")
    print("=" * 50)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
