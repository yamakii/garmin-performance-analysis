#!/usr/bin/env python3
"""Re-evaluate all activities using updated 2-month baseline models.

This script re-evaluates form metrics for all activities that have baselines
in form_baseline_history, using the new DuckDB-based evaluator.

Usage:
    uv run python tools/scripts/reevaluate_all_activities.py
    uv run python tools/scripts/reevaluate_all_activities.py --dry-run
    uv run python tools/scripts/reevaluate_all_activities.py --activity-ids 12345 67890
"""

import argparse
import sys
from pathlib import Path

import duckdb

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.form_baseline.evaluator import evaluate_and_store


def get_activities_to_reevaluate(db_path: str) -> list[tuple[int, str]]:
    """Get list of activities that can be re-evaluated.

    Returns activities that:
    1. Have splits data with form metrics
    2. Have a corresponding baseline in form_baseline_history

    Args:
        db_path: Path to DuckDB database

    Returns:
        List of (activity_id, activity_date) tuples
    """
    conn = duckdb.connect(db_path, read_only=True)

    try:
        result = conn.execute("""
            WITH activities_with_form AS (
                SELECT DISTINCT a.activity_id, a.activity_date
                FROM activities a
                JOIN splits s ON a.activity_id = s.activity_id
                WHERE s.ground_contact_time IS NOT NULL
                  AND s.vertical_oscillation IS NOT NULL
                  AND s.vertical_ratio IS NOT NULL
                  AND (EXTRACT(YEAR FROM a.activity_date) = 2021
                       OR EXTRACT(YEAR FROM a.activity_date) = 2025)
            )
            SELECT awf.activity_id, awf.activity_date
            FROM activities_with_form awf
            WHERE EXISTS (
                SELECT 1
                FROM form_baseline_history fbh
                WHERE fbh.period_start <= awf.activity_date
                  AND fbh.period_end >= awf.activity_date
                  AND fbh.user_id = 'default'
                  AND fbh.condition_group = 'flat_road'
            )
            ORDER BY awf.activity_date
        """).fetchall()

        return [(int(row[0]), str(row[1])) for row in result]

    finally:
        conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Re-evaluate all activities with updated 2-month baselines"
    )
    parser.add_argument(
        "--db-path",
        help="Path to DuckDB database (default: $GARMIN_DATA_DIR/database/garmin_performance.duckdb)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print activities to be re-evaluated without executing",
    )
    parser.add_argument(
        "--activity-ids",
        type=int,
        nargs="+",
        help="Re-evaluate specific activity IDs only",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Expand path
    import os

    if args.db_path:
        db_path = os.path.expanduser(args.db_path)
    else:
        garmin_data_dir = os.getenv(
            "GARMIN_DATA_DIR", os.path.expanduser("~/garmin_data")
        )
        db_path = f"{garmin_data_dir}/database/garmin_performance.duckdb"
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    # Get activities to re-evaluate
    print("Finding activities to re-evaluate...", file=sys.stderr)
    activities = get_activities_to_reevaluate(db_path)

    # Filter by specific IDs if requested
    if args.activity_ids:
        activities = [
            (aid, date) for aid, date in activities if aid in args.activity_ids
        ]

    if not activities:
        print("No activities to re-evaluate.", file=sys.stderr)
        return 0

    print(f"Found {len(activities)} activities to re-evaluate", file=sys.stderr)
    print()

    if args.dry_run:
        print("[DRY RUN MODE - No actual re-evaluation will occur]")
        print()
        for i, (activity_id, activity_date) in enumerate(activities, 1):
            print(f"[{i}/{len(activities)}] {activity_date}: {activity_id}")
        return 0

    # Re-evaluate each activity
    success_count = 0
    fail_count = 0

    for i, (activity_id, activity_date) in enumerate(activities, 1):
        print(
            f"[{i}/{len(activities)}] Re-evaluating {activity_date} (ID: {activity_id})...",
            end=" ",
            flush=True,
        )

        try:
            result = evaluate_and_store(
                activity_id=activity_id,
                activity_date=activity_date,
                db_path=db_path,
                condition_group="flat_road",
            )

            if args.verbose:
                print(f"\n  Overall: {result['overall_star_rating']}", end=" ")

            print("✓")
            success_count += 1

        except Exception as e:
            print("✗")
            print(f"  Error: {e}", file=sys.stderr)
            fail_count += 1

    # Summary
    print()
    print("=" * 60)
    print("Re-evaluation Summary:")
    print(f"  Total activities: {len(activities)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {fail_count}")
    print("=" * 60)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
