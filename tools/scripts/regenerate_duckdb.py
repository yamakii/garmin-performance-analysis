"""Regenerate DuckDB from existing raw data files.

This module provides functionality to regenerate DuckDB performance data
from existing raw data files WITHOUT making any API calls.

Key Features:
- Regenerate by date range or activity ID list
- Uses existing raw data (no API calls)
- Automatically generates performance.json as intermediate file
- Inserts into DuckDB normalized tables
- Skip activities with DuckDB cache (--delete-db to force)
- Dry run mode

Important Design Principles:
1. API Fetching and Data Regeneration are COMPLETELY SEPARATED
   - bulk_fetch_raw_data.py: Garmin API → raw data (with API calls)
   - regenerate_duckdb.py: raw data → DuckDB (NO API calls)

2. performance.json is an intermediate file
   - Automatically generated during DuckDB regeneration
   - No explicit Phase A (performance.json generation) needed
   - GarminIngestWorker.process_activity() generates it internally

3. Fetch only missing files
   - bulk_fetch_raw_data.py skips existing files (unless --force)
   - Avoids API rate limits

Usage:
    # Regenerate all activities
    python tools/scripts/regenerate_duckdb.py

    # Regenerate by date range
    python tools/scripts/regenerate_duckdb.py --start-date 2025-01-01 --end-date 2025-01-31

    # Regenerate specific activity IDs
    python tools/scripts/regenerate_duckdb.py --activity-ids 12345 67890

    # Delete old DuckDB before regeneration (complete reset)
    python tools/scripts/regenerate_duckdb.py --delete-db

    # Dry run (show what would be regenerated)
    python tools/scripts/regenerate_duckdb.py --dry-run
"""

import json
import logging
from pathlib import Path
from typing import Any

import duckdb
from tqdm import tqdm

from tools.database.db_reader import GarminDBReader
from tools.ingest.garmin_worker import GarminIngestWorker
from tools.utils.paths import get_database_dir, get_raw_dir

logger = logging.getLogger(__name__)


class DuckDBRegenerator:
    """Regenerate DuckDB from existing raw data files."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        db_path: Path | None = None,
        delete_old_db: bool = False,
        tables: list[str] | None = None,
        force: bool = False,
    ):
        """
        Initialize regenerator.

        Args:
            raw_dir: Raw data directory (default: from get_raw_dir())
            db_path: DuckDB path (default: from get_database_dir())
            delete_old_db: Delete existing DuckDB before regeneration
            tables: List of tables to regenerate (None = all tables)
            force: Delete existing records before re-insertion

        Raises:
            ValueError: If delete_old_db and tables are both specified
            ValueError: If force is True but tables is None
        """
        # Validation: delete_old_db and tables are mutually exclusive
        if delete_old_db and tables:
            raise ValueError(
                "--delete-db cannot be used with --tables. "
                "Database file deletion is only allowed for full regeneration (all tables). "
                "Use --force to delete existing records for specified activities instead."
            )

        # Validation: force requires tables
        if force and not tables:
            raise ValueError(
                "--force requires --tables. "
                "Use --force with --tables to delete existing records before re-insertion."
            )

        self.raw_dir = Path(raw_dir) if raw_dir else get_raw_dir()
        self.activity_dir = self.raw_dir / "activity"
        self.db_path = (
            Path(db_path)
            if db_path
            else get_database_dir() / "garmin_performance.duckdb"
        )
        self.delete_old_db = delete_old_db
        self.tables = tables
        self.force = force

        # Delete old DB if requested
        if self.delete_old_db and self.db_path.exists():
            logger.warning(f"Deleting existing DuckDB: {self.db_path}")
            self.db_path.unlink()

        self.db_reader = GarminDBReader(str(self.db_path))

    def filter_tables(self, tables: list[str] | None) -> list[str]:
        """
        Filter and validate table list.

        Args:
            tables: List of table names (None = all tables)

        Returns:
            Validated list of table names (always includes 'activities' except for body_composition only)

        Raises:
            ValueError: If invalid table names are provided
        """
        available_tables = [
            "activities",
            "splits",
            "form_efficiency",
            "hr_efficiency",
            "heart_rate_zones",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "time_series_metrics",
            "section_analyses",
            "body_composition",
        ]

        # If None, return all tables
        if tables is None:
            return available_tables

        # Validate table names
        invalid_tables = set(tables) - set(available_tables)
        if invalid_tables:
            raise ValueError(f"Invalid table names: {invalid_tables}")

        # Always include activities table (except for body_composition only)
        if tables == ["body_composition"]:
            return tables

        # Avoid duplicates - only add activities if not already present
        if "activities" not in tables:
            return ["activities"] + tables

        return tables

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

            # Try to read activity date from activity.json (summaryDTO)
            activity_json = activity_path / "activity.json"
            activity_date = None
            if activity_json.exists():
                try:
                    with open(activity_json, encoding="utf-8") as f:
                        activity_data = json.load(f)
                        # Extract date from summaryDTO (new structure)
                        summary = activity_data.get("summaryDTO", {})
                        if summary and "startTimeLocal" in summary:
                            activity_date = summary["startTimeLocal"].split("T")[0]
                        elif "startTimeLocal" in activity_data:
                            # Fallback to top-level (old structure)
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

    def get_activities_by_date_range(
        self, start_date: str, end_date: str
    ) -> list[tuple[int, str]]:
        """
        Get activity IDs from DuckDB by date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of (activity_id, activity_date) tuples
        """
        # Connect to DuckDB
        with duckdb.connect(str(self.db_reader.db_path), read_only=True) as conn:
            query = """
                SELECT activity_id, activity_date
                FROM activities
                WHERE activity_date BETWEEN ? AND ?
                ORDER BY activity_date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
            return [(row[0], str(row[1])) for row in results]

    def check_duckdb_cache(self, activity_id: int) -> bool:
        """
        Check if activity data exists in DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            True if activity data exists in DuckDB
        """
        with duckdb.connect(str(self.db_reader.db_path), read_only=True) as conn:
            query = "SELECT COUNT(*) FROM activities WHERE activity_id = ?"
            result = conn.execute(query, (activity_id,)).fetchone()
            return result[0] > 0 if result else False

    def check_raw_data_exists(self, activity_id: int) -> bool:
        """
        Check if raw data exists for activity.

        Args:
            activity_id: Activity ID

        Returns:
            True if raw data directory exists
        """
        activity_path = self.activity_dir / str(activity_id)
        return activity_path.exists()

    def regenerate_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Regenerate DuckDB data for a single activity from raw data.

        Process:
        1. Check if raw data exists
        2. Check DuckDB cache (skip if exists and delete_old_db=False)
        3. Use GarminIngestWorker.process_activity() to generate performance.json
        4. Automatically insert into DuckDB via save_data()

        Args:
            activity_id: Activity ID
            activity_date: Activity date (optional, for logging)

        Returns:
            Result dict with status and details
        """
        # Check if raw data exists
        if not self.check_raw_data_exists(activity_id):
            logger.warning(f"Raw data not found for activity {activity_id}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": "Raw data not found",
            }

        # Check DuckDB cache (skip if exists and delete_old_db=False)
        if not self.delete_old_db and self.check_duckdb_cache(activity_id):
            logger.debug(f"Skipping {activity_id}: DuckDB cache exists")
            return {
                "status": "skipped",
                "activity_id": activity_id,
                "activity_date": activity_date,
            }

        try:
            # Use GarminIngestWorker to regenerate
            worker = GarminIngestWorker()

            # process_activity() will:
            # 1. Load from cache (raw data)
            # 2. Generate performance.json
            # 3. Insert into DuckDB (via save_data())
            result = worker.process_activity(activity_id, activity_date or "")

            logger.info(
                f"Successfully regenerated DuckDB data for activity {activity_id}"
            )
            return {
                "status": "success",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "files": result,
            }

        except Exception as e:
            logger.error(f"Error regenerating data for activity {activity_id}: {e}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": str(e),
            }

    def regenerate_all(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        activity_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Regenerate DuckDB data for multiple activities.

        Args:
            start_date: Start date (YYYY-MM-DD) - mutually exclusive with activity_ids
            end_date: End date (YYYY-MM-DD) - mutually exclusive with activity_ids
            activity_ids: List of activity IDs - mutually exclusive with date range

        Returns:
            Summary dict with success/skip/error counts and details
        """
        # Validate arguments
        if activity_ids and (start_date or end_date):
            raise ValueError(
                "Cannot specify both activity_ids and date range. "
                "Use one or the other."
            )

        # Get activity list
        if activity_ids:
            activities: list[tuple[int, str | None]] = [
                (aid, None) for aid in activity_ids
            ]
            logger.info(f"Regenerating data for {len(activities)} specified activities")
        elif start_date and end_date:
            activities_from_db = self.get_activities_by_date_range(start_date, end_date)
            activities = list(activities_from_db)
            logger.info(
                f"Found {len(activities)} activities between {start_date} and {end_date}"
            )
        else:
            # Regenerate all activities from raw data
            activities = self.get_all_activities_from_raw()
            logger.info(f"Found {len(activities)} activities in raw data directory")

        if not activities:
            logger.info("No activities to regenerate")
            return {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "error": 0,
                "errors": [],
            }

        # Initialize counters
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        # Regenerate with progress bar
        for activity_id, activity_date in tqdm(
            activities, desc="Regenerating DuckDB data"
        ):
            result = self.regenerate_single_activity(activity_id, activity_date)

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
        }

        logger.info(
            f"Regeneration completed: {success_count} success, "
            f"{skip_count} skipped, {error_count} errors"
        )

        return summary


def main():
    """
    CLI entry point.

    Usage:
        # Regenerate all activities
        python tools/scripts/regenerate_duckdb.py

        # Regenerate by date range
        python tools/scripts/regenerate_duckdb.py --start-date 2025-01-01 --end-date 2025-01-31

        # Regenerate specific activities
        python tools/scripts/regenerate_duckdb.py --activity-ids 12345 67890

        # Regenerate specific tables only
        python tools/scripts/regenerate_duckdb.py --tables splits form_efficiency --activity-ids 12345

        # Force delete and re-insert specific tables
        python tools/scripts/regenerate_duckdb.py --tables splits --activity-ids 12345 --force

        # Delete old DuckDB before regeneration (full reset)
        python tools/scripts/regenerate_duckdb.py --delete-db

        # Dry run
        python tools/scripts/regenerate_duckdb.py --dry-run
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Regenerate DuckDB from existing raw data files (NO API calls)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--activity-ids",
        type=int,
        nargs="+",
        help="List of activity IDs (mutually exclusive with date range)",
    )
    parser.add_argument(
        "--tables",
        type=str,
        nargs="+",
        choices=[
            "activities",
            "splits",
            "form_efficiency",
            "hr_efficiency",
            "heart_rate_zones",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "time_series_metrics",
            "section_analyses",
            "body_composition",
        ],
        help="List of tables to regenerate (default: all tables)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete existing records for specified activity_ids/date range "
            "BEFORE re-insertion (requires --tables, use with caution)"
        ),
    )
    parser.add_argument(
        "--delete-db",
        action="store_true",
        help="Delete existing DuckDB before regeneration (complete reset, cannot be used with --tables)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be regenerated without actually regenerating",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.activity_ids and (args.start_date or args.end_date):
        parser.error(
            "Cannot specify both --activity-ids and date range. Use one or the other."
        )

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create regenerator (validation happens in __init__)
    try:
        regenerator = DuckDBRegenerator(
            delete_old_db=args.delete_db,
            tables=args.tables,
            force=args.force,
        )
    except ValueError as e:
        parser.error(str(e))

    if args.dry_run:
        # Dry run: scan and show what would be regenerated
        if args.activity_ids:
            activities: list[tuple[int, str | None]] = [
                (aid, None) for aid in args.activity_ids
            ]
        elif args.start_date and args.end_date:
            activities_from_db = regenerator.get_activities_by_date_range(
                args.start_date, args.end_date
            )
            activities = list(activities_from_db)
        else:
            activities = regenerator.get_all_activities_from_raw()

        print("\n=== Dry Run ===")
        print(f"Delete old DuckDB: {args.delete_db}")
        if args.tables:
            print(f"Tables to regenerate: {', '.join(args.tables)}")
        else:
            print("Tables to regenerate: all")
        print(f"Force delete existing records: {args.force}")
        print(f"Found {len(activities)} activities:")

        for activity_id, activity_date in activities[:10]:  # Show first 10
            # Check status
            raw_exists = regenerator.check_raw_data_exists(activity_id)
            cache_exists = regenerator.check_duckdb_cache(activity_id)

            status = []
            if not raw_exists:
                status.append("❌ No raw data")
            elif cache_exists and not args.delete_db and not args.force:
                status.append("⏭️  Skip (cache exists)")
            elif args.force:
                status.append("🔄 Will delete and regenerate")
            else:
                status.append("✅ Will regenerate")

            date_str = f" ({activity_date})" if activity_date else ""
            print(f"  - Activity {activity_id}{date_str}: {' '.join(status)}")

        if len(activities) > 10:
            print(f"  ... and {len(activities) - 10} more")

        return

    # Execute regeneration
    summary = regenerator.regenerate_all(
        start_date=args.start_date,
        end_date=args.end_date,
        activity_ids=args.activity_ids,
    )

    # Display summary
    print("\n=== Regeneration Summary ===")
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


if __name__ == "__main__":
    main()
