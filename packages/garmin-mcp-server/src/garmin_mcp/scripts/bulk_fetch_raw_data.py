"""Bulk fetch raw data files for multiple activities.

This module provides functionality to fetch missing raw data files from
Garmin Connect API with flexible filtering options.

Key Features:
- Fetch by date range or activity ID list
- Selective API type fetching (activity_details, splits, weather, etc.)
- Skip existing files (--force to re-fetch)
- Dry run mode
- Rate limit protection

Usage:
    # Fetch by date range (missing files only)
    python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31

    # Fetch specific API types only
    python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --api-types weather vo2_max

    # Fetch specific activity IDs
    python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --activity-ids 12345 67890 11111

    # Force re-fetch even if files exist
    python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --force

    # Dry run (show what would be fetched)
    python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --dry-run
"""

import logging
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.ingest.garmin_worker import GarminIngestWorker
from garmin_mcp.utils.paths import get_database_dir, get_raw_dir

logger = logging.getLogger(__name__)

# Supported API types
SUPPORTED_API_TYPES = [
    "activity_details",
    "splits",
    "weather",
    "gear",
    "hr_zones",
    "vo2_max",
    "lactate_threshold",
]


class BulkRawDataFetcher:
    """Bulk fetch raw data files from Garmin Connect API."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        db_path: Path | None = None,
        delay_seconds: float = 1.0,
        force: bool = False,
        api_types: list[str] | None = None,
    ):
        """
        Initialize fetcher.

        Args:
            raw_dir: Raw data directory (default: from get_raw_dir())
            db_path: DuckDB path (default: from get_database_dir())
            delay_seconds: Delay between API calls (rate limit protection)
            force: Force re-fetch even if file exists
            api_types: List of API types to fetch (default: all supported types)
        """
        self.raw_dir = Path(raw_dir) if raw_dir else get_raw_dir()
        self.activity_dir = self.raw_dir / "activity"
        db_path = (
            Path(db_path)
            if db_path
            else get_database_dir() / "garmin_performance.duckdb"
        )
        self.db_reader = GarminDBReader(str(db_path))
        self.delay_seconds = delay_seconds
        self.force = force
        self.api_types = api_types if api_types else SUPPORTED_API_TYPES

        # Validate API types
        invalid_types = set(self.api_types) - set(SUPPORTED_API_TYPES)
        if invalid_types:
            raise ValueError(
                f"Invalid API types: {invalid_types}. "
                f"Supported types: {SUPPORTED_API_TYPES}"
            )

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
        with get_connection(self.db_reader.db_path) as conn:
            query = """
                SELECT activity_id, activity_date
                FROM activities
                WHERE activity_date BETWEEN ? AND ?
                ORDER BY activity_date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
            return [(row[0], str(row[1])) for row in results]

    def check_missing_files(self, activity_id: int) -> dict[str, bool]:
        """
        Check which API files are missing for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            Dict mapping API type to missing status (True if missing)
        """
        activity_path = self.activity_dir / str(activity_id)
        missing = {}

        for api_type in self.api_types:
            file_path = activity_path / f"{api_type}.json"
            # Missing if: force=True OR file doesn't exist
            missing[api_type] = self.force or not file_path.exists()

        return missing

    def fetch_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch missing raw data files for a single activity.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (optional, for logging)

        Returns:
            Result dict with status and details
        """
        # Check which files are missing
        missing_files = self.check_missing_files(activity_id)
        files_to_fetch = [
            api for api, is_missing in missing_files.items() if is_missing
        ]

        if not files_to_fetch:
            logger.debug(f"Skipping {activity_id}: all files exist")
            return {
                "status": "skipped",
                "activity_id": activity_id,
                "activity_date": activity_date,
            }

        try:
            # Use GarminIngestWorker to fetch data
            worker = GarminIngestWorker()

            # Force refetch only the missing files
            worker.collect_data(
                activity_id,
                force_refetch=files_to_fetch if self.force else None,
            )

            logger.info(
                f"Successfully fetched {len(files_to_fetch)} files for activity {activity_id}: "
                f"{', '.join(files_to_fetch)}"
            )
            return {
                "status": "success",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "fetched_files": files_to_fetch,
            }

        except Exception as e:
            logger.error(f"Error fetching data for activity {activity_id}: {e}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": str(e),
            }

    def fetch_all(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        activity_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch missing raw data files for multiple activities.

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
            logger.info(f"Fetching data for {len(activities)} specified activities")
        elif start_date and end_date:
            activities_from_db = self.get_activities_by_date_range(start_date, end_date)
            activities = list(activities_from_db)
            logger.info(
                f"Found {len(activities)} activities between {start_date} and {end_date}"
            )
        else:
            raise ValueError("Must specify either activity_ids or date range")

        if not activities:
            logger.info("No activities to fetch")
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

        # Fetch with progress bar
        for activity_id, activity_date in tqdm(activities, desc="Fetching raw data"):
            result = self.fetch_single_activity(activity_id, activity_date)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
                skip_count += 1
            elif result["status"] == "error":
                error_count += 1
                errors.append(result)

            # Rate limit protection
            if self.delay_seconds > 0 and result["status"] != "skipped":
                time.sleep(self.delay_seconds)

        # Generate summary
        summary = {
            "total": len(activities),
            "success": success_count,
            "skipped": skip_count,
            "error": error_count,
            "errors": errors,
        }

        logger.info(
            f"Fetch completed: {success_count} success, "
            f"{skip_count} skipped, {error_count} errors"
        )

        return summary


def main():
    """
    CLI entry point.

    Usage:
        # Fetch by date range
        python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31

        # Fetch specific API types
        python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --api-types weather vo2_max

        # Fetch specific activities
        python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --activity-ids 12345 67890

        # Force re-fetch
        python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --force

        # Dry run
        python -m garmin_mcp.scripts.bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --dry-run
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Bulk fetch raw data files from Garmin Connect API"
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
        "--api-types",
        type=str,
        nargs="+",
        choices=SUPPORTED_API_TYPES,
        help=f"API types to fetch (default: all). Choices: {', '.join(SUPPORTED_API_TYPES)}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetch even if file exists",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without actually fetching",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.activity_ids and (args.start_date or args.end_date):
        parser.error(
            "Cannot specify both --activity-ids and date range. Use one or the other."
        )
    if not args.activity_ids and not (args.start_date and args.end_date):
        parser.error(
            "Must specify either --activity-ids or both --start-date and --end-date"
        )

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create fetcher
    fetcher = BulkRawDataFetcher(
        delay_seconds=args.delay,
        force=args.force,
        api_types=args.api_types,
    )

    if args.dry_run:
        # Dry run: scan and show what would be fetched
        if args.activity_ids:
            activities: list[tuple[int, str | None]] = [
                (aid, None) for aid in args.activity_ids
            ]
        else:
            activities_from_db = fetcher.get_activities_by_date_range(
                args.start_date, args.end_date
            )
            activities = list(activities_from_db)

        print("\n=== Dry Run ===")
        print(f"API types to fetch: {', '.join(fetcher.api_types)}")
        print(f"Force re-fetch: {args.force}")
        print(f"Found {len(activities)} activities:")

        for activity_id, activity_date in activities[:10]:  # Show first 10
            missing_files = fetcher.check_missing_files(activity_id)
            files_to_fetch = [
                api for api, is_missing in missing_files.items() if is_missing
            ]
            if files_to_fetch:
                date_str = f" ({activity_date})" if activity_date else ""
                print(
                    f"  - Activity {activity_id}{date_str}: {', '.join(files_to_fetch)}"
                )

        if len(activities) > 10:
            print(f"  ... and {len(activities) - 10} more")

        return

    # Execute fetch
    summary = fetcher.fetch_all(
        start_date=args.start_date,
        end_date=args.end_date,
        activity_ids=args.activity_ids,
    )

    # Display summary
    print("\n=== Fetch Summary ===")
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
