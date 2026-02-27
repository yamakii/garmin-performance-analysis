"""Batch generate reports for activities with completed section analyses.

Checks DuckDB for activities that have all 5 section analyses completed,
then generates Markdown reports for each.

Usage:
    # By date range
    uv run python -m garmin_mcp.scripts.batch_generate_reports.py \
        --start-date 2025-12-26 --end-date 2026-02-13

    # From batch_ingest output
    uv run python -m garmin_mcp.scripts.batch_generate_reports.py \
        --activity-list /tmp/batch_activity_list.json

    # Dry run
    uv run python -m garmin_mcp.scripts.batch_generate_reports.py \
        --start-date 2025-12-26 --end-date 2026-02-13 --dry-run
"""

import json
import logging

from garmin_mcp.database.connection import get_connection
from garmin_mcp.reporting.report_generator_worker import ReportGeneratorWorker
from garmin_mcp.utils.paths import get_database_dir

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = {"efficiency", "environment", "phase", "split", "summary"}


def get_section_completeness(
    db_path: str, activity_ids: list[int]
) -> dict[int, set[str]]:
    """
    Check which section types exist for each activity.

    Returns:
        Dict mapping activity_id to set of completed section types
    """
    if not activity_ids:
        return {}

    with get_connection(db_path) as conn:
        placeholders = ", ".join(["?"] * len(activity_ids))
        rows = conn.execute(
            f"SELECT activity_id, section_type FROM section_analyses "
            f"WHERE activity_id IN ({placeholders})",
            activity_ids,
        ).fetchall()

    result: dict[int, set[str]] = {}
    for activity_id, section_type in rows:
        result.setdefault(activity_id, set()).add(section_type)
    return result


def get_activities_by_date_range(
    db_path: str, start_date: str, end_date: str
) -> list[tuple[int, str]]:
    """Get (activity_id, date) pairs from DuckDB."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT activity_id, activity_date FROM activities "
            "WHERE activity_date BETWEEN ? AND ? ORDER BY activity_date",
            [start_date, end_date],
        ).fetchall()
    return [(row[0], str(row[1])) for row in rows]


def load_activity_list(path: str) -> list[tuple[int, str]]:
    """Load activity list from batch_ingest output JSON."""
    with open(path) as f:
        data = json.load(f)
    return [
        (item["activity_id"], item["date"])
        for item in data
        if item.get("status") == "success" and item.get("activity_id")
    ]


def batch_generate_reports(
    activities: list[tuple[int, str]],
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Generate reports for activities with complete section analyses.

    Args:
        activities: List of (activity_id, date) tuples
        db_path: DuckDB path (default: auto-detect)
        dry_run: If True, only show what would be generated

    Returns:
        Summary dict with counts
    """
    if db_path is None:
        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    activity_ids = [aid for aid, _ in activities]
    completeness = get_section_completeness(db_path, activity_ids)

    # Classify activities
    ready = []
    incomplete = []
    for activity_id, date_str in activities:
        sections = completeness.get(activity_id, set())
        missing = REQUIRED_SECTIONS - sections
        if not missing:
            ready.append((activity_id, date_str))
        else:
            incomplete.append((activity_id, date_str, missing))

    if dry_run:
        print("\n=== Dry Run ===")
        print(f"Total activities: {len(activities)}")
        print(f"Ready for report: {len(ready)}")
        print(f"Incomplete analyses: {len(incomplete)}")
        if incomplete:
            print("\nIncomplete:")
            for aid, d, missing in incomplete:
                print(f"  Activity {aid} ({d}): missing {', '.join(sorted(missing))}")
        if ready:
            print("\nReady:")
            for aid, d in ready:
                print(f"  Activity {aid} ({d})")
        return {
            "total": len(activities),
            "ready": len(ready),
            "incomplete": len(incomplete),
        }

    if not ready:
        print("No activities ready for report generation.")
        return {
            "total": len(activities),
            "generated": 0,
            "skipped": len(incomplete),
            "errors": 0,
        }

    worker = ReportGeneratorWorker(db_path=db_path)
    generated = 0
    errors = 0

    print(f"\n=== Generating {len(ready)} reports ===")
    for i, (activity_id, date_str) in enumerate(ready, 1):
        print(
            f"[{i}/{len(ready)}] Activity {activity_id} ({date_str})...",
            end=" ",
            flush=True,
        )
        try:
            result = worker.generate_report(activity_id, date_str)
            report_path = result.get("report_path", "unknown")
            print(f"OK → {report_path}")
            generated += 1
        except Exception as e:
            print(f"ERROR: {e}")
            logger.error(
                f"Report generation failed for {activity_id}: {e}", exc_info=True
            )
            errors += 1

    if incomplete:
        print(f"\nSkipped {len(incomplete)} activities with incomplete analyses:")
        for aid, d, missing in incomplete:
            print(f"  Activity {aid} ({d}): missing {', '.join(sorted(missing))}")

    print("\n=== Summary ===")
    print(f"Generated: {generated}")
    print(f"Skipped (incomplete): {len(incomplete)}")
    print(f"Errors: {errors}")

    return {
        "total": len(activities),
        "generated": generated,
        "skipped": len(incomplete),
        "errors": errors,
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch generate reports for analyzed activities"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--activity-list",
        type=str,
        help="Path to batch_ingest output JSON",
    )
    group.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD), requires --end-date",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without generating",
    )

    args = parser.parse_args()

    if args.start_date and not args.end_date:
        parser.error("--start-date requires --end-date")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    db_path = str(get_database_dir() / "garmin_performance.duckdb")

    if args.activity_list:
        activities = load_activity_list(args.activity_list)
    else:
        activities = get_activities_by_date_range(
            db_path, args.start_date, args.end_date
        )

    if not activities:
        print("No activities found.")
        return

    batch_generate_reports(activities, db_path=db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
