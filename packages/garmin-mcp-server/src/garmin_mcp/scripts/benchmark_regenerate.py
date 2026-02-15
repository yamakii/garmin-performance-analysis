#!/usr/bin/env python3
"""Benchmark script for DuckDB regeneration performance.

Usage:
    python -m garmin_mcp.scripts.benchmark_regenerate.py --num-activities 10
"""

import argparse
import logging
import time

from garmin_mcp.scripts.regenerate_duckdb import DuckDBRegenerator
from garmin_mcp.utils.paths import get_database_dir, get_raw_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def benchmark_regeneration(
    num_activities: int = 10,
    tables: list[str] | None = None,
    force: bool = True,
) -> dict:
    """
    Benchmark DuckDB regeneration performance.

    Args:
        num_activities: Number of activities to regenerate
        tables: List of tables to regenerate (None = all tables)
        force: Whether to force deletion before insertion

    Returns:
        Dict with timing results
    """
    import json

    # Get activity list from raw data
    raw_dir = get_raw_dir()
    activity_dir = raw_dir / "activity"

    activities = []
    for activity_path in sorted(activity_dir.iterdir()):
        if activity_path.is_dir() and activity_path.name.isdigit():
            activity_id = int(activity_path.name)

            # Extract date from activity.json
            activity_json = activity_path / "activity.json"
            activity_date = None
            if activity_json.exists():
                try:
                    with open(activity_json, encoding="utf-8") as f:
                        activity_data = json.load(f)
                        # Extract date from summaryDTO
                        summary = activity_data.get("summaryDTO", {})
                        if summary and "startTimeLocal" in summary:
                            activity_date = summary["startTimeLocal"].split("T")[0]
                except Exception as e:
                    logger.warning(f"Could not read date from {activity_json}: {e}")

            if activity_date:
                activities.append((activity_id, activity_date))
                if len(activities) >= num_activities:
                    break

    if len(activities) < num_activities:
        logger.warning(
            f"Only found {len(activities)} activities, requested {num_activities}"
        )

    activity_ids = [a[0] for a in activities]
    logger.info(f"Benchmarking with {len(activities)} activities")
    logger.info(f"Activity IDs: {activity_ids}")
    logger.info(f"Tables: {tables or 'all'}")
    logger.info(f"Force deletion: {force}")

    # Create a test database (use production DB path for schema compatibility)
    test_db_path = get_database_dir() / "test_performance.duckdb"
    if test_db_path.exists():
        test_db_path.unlink()
        logger.info(f"Deleted existing test database: {test_db_path}")

    # Create regenerator with delete_old_db=False to avoid deleting during init
    # We'll let the first insertion create the database
    regenerator = DuckDBRegenerator(
        db_path=test_db_path,
        delete_old_db=False,
        tables=tables,
    )

    # Start timing
    start_time = time.time()

    # Phase 1: Deletion (if force=True)
    # Skip deletion for first run since DB doesn't exist yet
    deletion_time = 0.0

    # Phase 2: Regeneration (this will create the DB)
    regeneration_start = time.time()
    summary = regenerator.regenerate_all(activity_ids=activity_ids)
    regeneration_time = time.time() - regeneration_start

    # Total time
    total_time = time.time() - start_time

    # Calculate per-activity time
    per_activity_time = total_time / len(activities) if activities else 0

    results = {
        "num_activities": len(activities),
        "activity_ids": activity_ids,
        "tables": tables or "all",
        "force": force,
        "deletion_time": deletion_time,
        "regeneration_time": regeneration_time,
        "total_time": total_time,
        "per_activity_time": per_activity_time,
        "success_count": summary["success"],
        "error_count": summary["error"],
    }

    # Log results
    logger.info("=" * 60)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 60)
    logger.info(f"Activities: {len(activities)}")
    logger.info(f"Tables: {tables or 'all'}")
    logger.info(f"Force deletion: {force}")
    logger.info(f"Deletion time: {deletion_time:.2f}s")
    logger.info(f"Regeneration time: {regeneration_time:.2f}s")
    logger.info(f"Total time: {total_time:.2f}s")
    logger.info(f"Per-activity time: {per_activity_time:.2f}s")
    logger.info(f"Success: {summary['success']}, Errors: {summary['error']}")
    logger.info("=" * 60)

    # Extrapolate to 106 activities
    if len(activities) > 0:
        estimated_106 = per_activity_time * 106
        logger.info(
            f"Estimated time for 106 activities: {estimated_106:.2f}s ({estimated_106/60:.2f} minutes)"
        )

    # Cleanup
    if test_db_path.exists():
        test_db_path.unlink()
        logger.info(f"Cleaned up test database: {test_db_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Benchmark DuckDB regeneration")
    parser.add_argument(
        "--num-activities",
        type=int,
        default=10,
        help="Number of activities to benchmark (default: 10)",
    )
    parser.add_argument(
        "--tables",
        type=str,
        nargs="+",
        help="Tables to regenerate (default: all)",
    )
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Disable force deletion (default: enabled)",
    )

    args = parser.parse_args()

    benchmark_regeneration(
        num_activities=args.num_activities,
        tables=args.tables,
        force=not args.no_force,
    )


if __name__ == "__main__":
    main()
