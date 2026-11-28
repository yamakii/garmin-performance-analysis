#!/usr/bin/env python3
"""Re-evaluate all activities using updated 2-month baseline models.

This script re-evaluates form metrics for all activities that have baselines
in form_baseline_history, using the new DuckDB-based evaluator.

Usage:
    uv run python -m garmin_mcp.scripts.reevaluate_all_activities.py
    uv run python -m garmin_mcp.scripts.reevaluate_all_activities.py --dry-run
    uv run python -m garmin_mcp.scripts.reevaluate_all_activities.py --activity-ids 12345 67890
"""

import argparse
import sys
from pathlib import Path

from garmin_mcp.database.connection import get_connection
from garmin_mcp.form_baseline.data_fetcher import AllSplitsSuspectError
from garmin_mcp.form_baseline.evaluator import evaluate_and_store


def get_activities_to_reevaluate(
    db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[int, str]]:
    """Get list of activities that can be re-evaluated.

    Returns activities that:
    1. Have splits data with form metrics
    2. Have a baseline in form_baseline_history trained on the activity's own
       dynamics sensor (NULL sensor -> the legacy ``'all'`` model, #1631)
    3. Fall inside the optional ``start_date`` / ``end_date`` (inclusive)

    Args:
        db_path: Path to DuckDB database
        start_date: Earliest activity date (YYYY-MM-DD), or None
        end_date: Latest activity date (YYYY-MM-DD), or None

    Returns:
        List of (activity_id, activity_date) tuples
    """
    date_clause = ""
    params: list[str] = []
    if start_date:
        date_clause += " AND a.activity_date >= CAST(? AS DATE)"
        params.append(start_date)
    if end_date:
        date_clause += " AND a.activity_date <= CAST(? AS DATE)"
        params.append(end_date)

    with get_connection(db_path) as conn:
        result = conn.execute(
            f"""
            WITH activities_with_form AS (
                SELECT DISTINCT a.activity_id, a.activity_date,
                       COALESCE(a.dynamics_source, 'all') AS dynamics_source
                FROM activities a
                JOIN splits s ON a.activity_id = s.activity_id
                WHERE s.ground_contact_time IS NOT NULL
                  AND s.vertical_oscillation IS NOT NULL
                  AND s.vertical_ratio IS NOT NULL
                  {date_clause}
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
                  AND fbh.dynamics_source = awf.dynamics_source
            )
            ORDER BY awf.activity_date
            """,
            params,
        ).fetchall()

        return [(int(row[0]), str(row[1])) for row in result]


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
        "--start-date",
        help="Only activities on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        help="Only activities on or before this date (YYYY-MM-DD)",
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
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()
    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        return 1

    # Get activities to re-evaluate
    print("Finding activities to re-evaluate...", file=sys.stderr)
    activities = get_activities_to_reevaluate(
        db_path, start_date=args.start_date, end_date=args.end_date
    )

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

    counts = reevaluate(activities, db_path, verbose=args.verbose)

    # Summary
    print()
    print("=" * 60)
    print("Re-evaluation Summary:")
    print(f"  Total activities: {len(activities)}")
    print(f"  Successful: {counts['success']}")
    print(f"  Skipped (all splits dynamics_suspect): {counts['skipped']}")
    print(f"  Failed: {counts['failed']}")
    print("=" * 60)

    return 0 if counts["failed"] == 0 else 1


def reevaluate(
    activities: list[tuple[int, str]], db_path: str, verbose: bool = False
) -> dict[str, int]:
    """Re-evaluate each ``(activity_id, activity_date)``; return outcome counts.

    A run whose every split is ``dynamics_suspect`` has no trustworthy form
    average: it is counted as ``skipped``, not ``failed`` (#1637), and its old
    grade has already been removed by :func:`evaluate_and_store`.
    """
    counts = {"success": 0, "skipped": 0, "failed": 0}
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

            if verbose:
                print(f"\n  Overall: {result['overall_star_rating']}", end=" ")

            print("\u2713")
            counts["success"] += 1

        except AllSplitsSuspectError:
            print("- (all splits dynamics_suspect)")
            counts["skipped"] += 1

        except Exception as e:
            print("\u2717")
            print(f"  Error: {e}", file=sys.stderr)
            counts["failed"] += 1
    return counts


if __name__ == "__main__":
    sys.exit(main())
