"""Migrate time series data from activity_details.json to DuckDB.

This script migrates second-by-second time series data (26 metrics × 1000-2000 seconds)
from raw activity_details.json files into the time_series_metrics DuckDB table.

Key Features:
- Migrate all activities or specific activity IDs
- Dry run mode to preview migration
- Data integrity verification
- Progress tracking with tqdm
- Error handling (skip and continue)

Usage:
    # Migrate all activities
    python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py

    # Migrate specific activity IDs
    python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --activity-ids 12345 67890

    # Dry run (show what would be migrated)
    python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --dry-run

    # Verify integrity after migration
    python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --verify

Design:
    - Separation of concerns: Migration vs Verification
    - Uses TimeSeriesMetricsInserter for actual DuckDB insertion
    - Scans raw data directory for activities with activity_details.json
    - Progress tracking for large-scale migrations (103 activities)
"""

import json
import logging
from pathlib import Path
from typing import Any

import duckdb
from tqdm import tqdm

from garmin_mcp.database.inserters.time_series_metrics import insert_time_series_metrics
from garmin_mcp.utils.paths import get_database_dir, get_raw_dir

logger = logging.getLogger(__name__)


class TimeSeriesMigrator:
    """Migrate time series data from activity_details.json to DuckDB."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        db_path: Path | None = None,
    ):
        """
        Initialize migrator.

        Args:
            raw_dir: Raw data directory (default: from get_raw_dir())
            db_path: DuckDB path (default: from get_database_dir())
        """
        self.raw_dir = Path(raw_dir) if raw_dir else get_raw_dir()
        self.activity_dir = self.raw_dir / "activity"
        self.db_path = (
            Path(db_path)
            if db_path
            else get_database_dir() / "garmin_performance.duckdb"
        )

    def get_all_activities_from_raw(self) -> list[tuple[int, str | None]]:
        """
        Scan raw data directory and get all activity IDs.

        Returns:
            List of (activity_id, activity_date) tuples
            activity_date may be None if activity.json doesn't exist
        """
        activities: list[tuple[int, str | None]] = []

        if not self.activity_dir.exists():
            logger.warning(f"Activity directory not found: {self.activity_dir}")
            return activities

        for activity_path in self.activity_dir.iterdir():
            if not activity_path.is_dir():
                continue

            # Skip special directories
            if activity_path.name.startswith("."):
                continue

            # Extract activity_id from directory name
            try:
                activity_id = int(activity_path.name)
            except ValueError:
                logger.debug(f"Skipping {activity_path.name}: invalid activity ID")
                continue

            # Try to read activity date from activity.json
            activity_json = activity_path / "activity.json"
            activity_date = None
            if activity_json.exists():
                try:
                    with open(activity_json, encoding="utf-8") as f:
                        activity_data = json.load(f)
                        # Extract date from startTimeLocal or beginTimestamp
                        if "startTimeLocal" in activity_data:
                            activity_date = activity_data["startTimeLocal"].split(" ")[
                                0
                            ]
                        elif "beginTimestamp" in activity_data:
                            activity_date = activity_data["beginTimestamp"].split("T")[
                                0
                            ]
                except Exception as e:
                    logger.debug(
                        f"Could not read activity date from {activity_json}: {e}"
                    )

            activities.append((activity_id, activity_date))

        return activities

    def check_activity_details_exists(self, activity_id: int) -> bool:
        """
        Check if activity_details.json exists for activity.

        Args:
            activity_id: Activity ID

        Returns:
            True if activity_details.json exists
        """
        activity_path = self.activity_dir / str(activity_id)
        activity_details_path = activity_path / "activity_details.json"
        return activity_details_path.exists()

    def get_activity_details_path(self, activity_id: int) -> Path:
        """
        Get path to activity_details.json.

        Args:
            activity_id: Activity ID

        Returns:
            Path to activity_details.json
        """
        return self.activity_dir / str(activity_id) / "activity_details.json"

    def count_data_points_in_raw(self, activity_id: int) -> int:
        """
        Count data points in activity_details.json.

        Args:
            activity_id: Activity ID

        Returns:
            Number of data points in activityDetailMetrics array
        """
        activity_details_path = self.get_activity_details_path(activity_id)

        try:
            with open(activity_details_path, encoding="utf-8") as f:
                activity_details = json.load(f)
                metrics = activity_details.get("activityDetailMetrics", [])
                return len(metrics)
        except Exception as e:
            logger.error(f"Error reading {activity_details_path}: {e}")
            return 0

    def count_data_points_in_duckdb(self, activity_id: int) -> int:
        """
        Count data points in DuckDB for activity.

        Args:
            activity_id: Activity ID

        Returns:
            Number of data points in time_series_metrics table
        """
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?",
                [activity_id],
            ).fetchone()
            conn.close()
            if result is None:
                return 0
            return int(result[0])
        except Exception as e:
            logger.debug(f"Error counting data points for {activity_id}: {e}")
            return 0

    def migrate_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Migrate time series data for a single activity.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (optional, for logging)

        Returns:
            Result dict with status and details
        """
        # Check if activity_details.json exists
        if not self.check_activity_details_exists(activity_id):
            logger.warning(
                f"activity_details.json not found for activity {activity_id}"
            )
            return {
                "status": "skipped",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "reason": "activity_details.json not found",
            }

        try:
            # Get activity_details.json path
            activity_details_path = self.get_activity_details_path(activity_id)

            # Count data points before migration
            data_points = self.count_data_points_in_raw(activity_id)

            # Use TimeSeriesMetricsInserter to insert data
            success = insert_time_series_metrics(
                activity_details_file=str(activity_details_path),
                activity_id=activity_id,
                db_path=str(self.db_path),
            )

            if not success:
                return {
                    "status": "error",
                    "activity_id": activity_id,
                    "activity_date": activity_date,
                    "error": "insert_time_series_metrics returned False",
                }

            logger.info(
                f"Successfully migrated {data_points} data points for activity {activity_id}"
            )
            return {
                "status": "success",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "data_points": data_points,
            }

        except Exception as e:
            logger.error(f"Error migrating activity {activity_id}: {e}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": str(e),
            }

    def migrate_all(
        self,
        activity_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Migrate time series data for multiple activities.

        Args:
            activity_ids: List of activity IDs (None = all activities)
            dry_run: If True, only scan without migrating

        Returns:
            Summary dict with success/skip/error counts and details
        """
        # Get activity list
        if activity_ids:
            activities: list[tuple[int, str | None]] = [
                (aid, None) for aid in activity_ids
            ]
            logger.info(f"Migrating {len(activities)} specified activities")
        else:
            # Scan all activities from raw data
            activities = self.get_all_activities_from_raw()
            logger.info(f"Found {len(activities)} activities in raw data directory")

        if not activities:
            logger.info("No activities to migrate")
            return {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "error": 0,
                "errors": [],
                "dry_run": dry_run,
            }

        # Filter activities with activity_details.json
        activities_with_details = [
            (aid, date)
            for aid, date in activities
            if self.check_activity_details_exists(aid)
        ]

        if dry_run:
            logger.info(
                f"[DRY RUN] Would migrate {len(activities_with_details)} activities "
                f"with activity_details.json"
            )
            return {
                "total": len(activities),
                "activities_with_details": len(activities_with_details),
                "dry_run": True,
            }

        # Initialize counters
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        # Migrate with progress bar
        for activity_id, activity_date in tqdm(
            activities, desc="Migrating time series data"
        ):
            result = self.migrate_single_activity(activity_id, activity_date)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
                skip_count += 1
            elif result["status"] == "error":
                error_count += 1
                errors.append(result)

        # Generate summary
        summary = {
            "total": len(activities),
            "success": success_count,
            "skipped": skip_count,
            "error": error_count,
            "errors": errors,
            "dry_run": False,
        }

        logger.info(
            f"Migration completed: {success_count} success, "
            f"{skip_count} skipped, {error_count} errors"
        )

        return summary

    def verify_integrity(
        self,
        activity_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Verify data integrity after migration.

        Checks that the number of data points in DuckDB matches
        the number in activity_details.json for each activity.

        Args:
            activity_ids: List of activity IDs (None = all activities in DuckDB)

        Returns:
            Integrity verification result dict
        """
        # Get activity list from DuckDB
        if activity_ids:
            activities_to_verify = activity_ids
        else:
            # Get all activities from DuckDB
            try:
                conn = duckdb.connect(str(self.db_path), read_only=True)
                results = conn.execute(
                    "SELECT DISTINCT activity_id FROM time_series_metrics"
                ).fetchall()
                conn.close()
                activities_to_verify = [row[0] for row in results]
            except Exception as e:
                logger.error(f"Error querying DuckDB: {e}")
                return {
                    "total_activities": 0,
                    "verified": 0,
                    "mismatches": 0,
                    "errors": [{"error": str(e)}],
                }

        logger.info(f"Verifying integrity for {len(activities_to_verify)} activities")

        verified = 0
        mismatches = 0
        mismatch_details = []
        errors = []

        # Verify each activity
        for activity_id in tqdm(activities_to_verify, desc="Verifying integrity"):
            try:
                # Check if activity_details.json exists
                if not self.check_activity_details_exists(activity_id):
                    errors.append(
                        {
                            "activity_id": activity_id,
                            "error": "activity_details.json not found",
                        }
                    )
                    continue

                # Count data points in both sources
                expected = self.count_data_points_in_raw(activity_id)
                actual = self.count_data_points_in_duckdb(activity_id)

                if expected == actual:
                    verified += 1
                else:
                    mismatches += 1
                    mismatch_details.append(
                        {
                            "activity_id": activity_id,
                            "expected": expected,
                            "actual": actual,
                        }
                    )

            except Exception as e:
                errors.append(
                    {
                        "activity_id": activity_id,
                        "error": str(e),
                    }
                )

        # Generate summary
        result = {
            "total_activities": len(activities_to_verify),
            "verified": verified,
            "mismatches": mismatches,
            "mismatch_details": mismatch_details,
            "errors": errors,
        }

        if mismatches == 0 and not errors:
            logger.info(f"✅ Integrity verified: All {verified} activities match")
        else:
            logger.warning(
                f"⚠️ Integrity check: {verified} verified, "
                f"{mismatches} mismatches, {len(errors)} errors"
            )

        return result


def main():
    """
    CLI entry point.

    Usage:
        # Migrate all activities
        python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py

        # Migrate specific activities
        python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --activity-ids 12345 67890

        # Dry run
        python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --dry-run

        # Verify integrity
        python -m garmin_mcp.scripts.migrate_time_series_to_duckdb.py --verify
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate time series data from activity_details.json to DuckDB"
    )
    parser.add_argument(
        "--activity-ids",
        type=int,
        nargs="+",
        help="List of activity IDs to migrate (default: all activities)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify data integrity after migration (or verify only if used alone)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create migrator
    migrator = TimeSeriesMigrator()

    # Verify-only mode
    if args.verify and not args.dry_run and not args.activity_ids:
        result = migrator.verify_integrity()

        print("\n=== Integrity Verification ===")
        print(f"Total activities: {result['total_activities']}")
        print(f"Verified: {result['verified']}")
        print(f"Mismatches: {result['mismatches']}")

        if result["mismatch_details"]:
            print("\n=== Mismatch Details ===")
            for detail in result["mismatch_details"]:
                print(
                    f"  - Activity {detail['activity_id']}: "
                    f"expected {detail['expected']}, actual {detail['actual']}"
                )

        if result["errors"]:
            print("\n=== Errors ===")
            for error in result["errors"]:
                print(f"  - Activity {error['activity_id']}: {error['error']}")

        return

    # Dry run mode
    if args.dry_run:
        summary = migrator.migrate_all(
            activity_ids=args.activity_ids,
            dry_run=True,
        )

        print("\n=== Dry Run ===")
        print(f"Total activities: {summary['total']}")
        print(
            f"Activities with activity_details.json: {summary['activities_with_details']}"
        )
        print(f"Would migrate: {summary['activities_with_details']} activities")

        return

    # Execute migration
    summary = migrator.migrate_all(activity_ids=args.activity_ids)

    # Display summary
    print("\n=== Migration Summary ===")
    print(f"Total activities: {summary['total']}")
    print(f"Success: {summary['success']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Errors: {summary['error']}")

    if summary["errors"]:
        print("\n=== Error Details ===")
        for error in summary["errors"]:
            activity_id = error["activity_id"]
            date_str = (
                f" ({error['activity_date']})" if error.get("activity_date") else ""
            )
            print(f"  - Activity {activity_id}{date_str}: {error['error']}")

    # Auto-verify after migration
    if args.verify:
        print("\n=== Running Integrity Verification ===")
        result = migrator.verify_integrity()

        print(f"Total activities: {result['total_activities']}")
        print(f"Verified: {result['verified']}")
        print(f"Mismatches: {result['mismatches']}")

        if result["mismatch_details"]:
            print("\n=== Mismatch Details ===")
            for detail in result["mismatch_details"]:
                print(
                    f"  - Activity {detail['activity_id']}: "
                    f"expected {detail['expected']}, actual {detail['actual']}"
                )


if __name__ == "__main__":
    main()
