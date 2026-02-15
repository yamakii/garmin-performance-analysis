"""Batch ingest activities for a date range.

Fetches raw data from Garmin API and inserts into DuckDB for each date
in the specified range. Outputs a JSON list of results for downstream
batch analysis.

Usage:
    # Full run
    uv run python tools/scripts/batch_ingest.py \
        --start-date 2025-12-26 --end-date 2026-02-13

    # Dry run (show dates only)
    uv run python tools/scripts/batch_ingest.py \
        --start-date 2025-12-26 --end-date 2026-02-13 --dry-run

    # Custom output path
    uv run python tools/scripts/batch_ingest.py \
        --start-date 2025-12-26 --end-date 2026-02-13 \
        --output /tmp/my_batch.json
"""

import json
import logging
import time
from datetime import date, datetime, timedelta

from tools.planner.workflow_planner import WorkflowPlanner

logger = logging.getLogger(__name__)


def date_range(start: date, end: date):
    """Yield each date from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def batch_ingest(
    start_date: str,
    end_date: str,
    delay_seconds: float = 2.0,
    dry_run: bool = False,
    output_path: str = "/tmp/batch_activity_list.json",
) -> list[dict]:
    """
    Run WorkflowPlanner.execute_full_workflow for each date in range.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        delay_seconds: Delay between API calls
        dry_run: If True, only list dates without processing
        output_path: Path to write results JSON

    Returns:
        List of result dicts with activity_id, date, status
    """
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    dates = list(date_range(start, end))

    if dry_run:
        print(f"\n=== Dry Run: {len(dates)} dates ===")
        for d in dates:
            print(f"  {d.isoformat()}")
        return []

    planner = WorkflowPlanner()
    results: list[dict] = []

    print(f"\n=== Batch Ingest: {len(dates)} dates ===")
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        print(f"[{i}/{len(dates)}] Processing {date_str}...", end=" ", flush=True)

        try:
            result = planner.execute_full_workflow(date_str)
            activity_id = result["activity_id"]
            print(f"OK (activity_id={activity_id})")
            results.append(
                {
                    "activity_id": activity_id,
                    "date": date_str,
                    "status": "success",
                }
            )
        except ValueError as e:
            error_msg = str(e)
            if "no activit" in error_msg.lower():
                print("no activity (rest day)")
                results.append(
                    {
                        "activity_id": None,
                        "date": date_str,
                        "status": "no_activity",
                    }
                )
            elif "multiple" in error_msg.lower() or "Multiple" in error_msg:
                print("MULTIPLE ACTIVITIES - manual handling needed")
                logger.warning(f"Multiple activities on {date_str}: {e}")
                results.append(
                    {
                        "activity_id": None,
                        "date": date_str,
                        "status": "multiple_activities",
                        "error": error_msg,
                    }
                )
            else:
                print(f"ERROR: {e}")
                logger.error(f"ValueError for {date_str}: {e}")
                results.append(
                    {
                        "activity_id": None,
                        "date": date_str,
                        "status": "error",
                        "error": error_msg,
                    }
                )
        except Exception as e:
            print(f"ERROR: {e}")
            logger.error(f"Unexpected error for {date_str}: {e}", exc_info=True)
            results.append(
                {
                    "activity_id": None,
                    "date": date_str,
                    "status": "error",
                    "error": str(e),
                }
            )

        # Rate limit protection (skip delay on last item and rest days)
        if i < len(dates) and results[-1]["status"] == "success":
            time.sleep(delay_seconds)

    # Write results
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    no_activity = sum(1 for r in results if r["status"] == "no_activity")
    errors = sum(1 for r in results if r["status"] in ("error", "multiple_activities"))

    print("\n=== Summary ===")
    print(f"Total dates: {len(dates)}")
    print(f"Success: {success}")
    print(f"No activity: {no_activity}")
    print(f"Errors: {errors}")
    print(f"Results written to: {output_path}")

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch ingest activities for a date range"
    )
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show dates without processing",
    )
    parser.add_argument(
        "--output",
        default="/tmp/batch_activity_list.json",
        help="Output JSON path (default: /tmp/batch_activity_list.json)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    batch_ingest(
        start_date=args.start_date,
        end_date=args.end_date,
        delay_seconds=args.delay,
        dry_run=args.dry_run,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
