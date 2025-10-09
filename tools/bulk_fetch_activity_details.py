"""Bulk fetch activity_details.json for multiple activities.

This module provides the ActivityDetailsFetcher class to fetch
activity_details.json files for all activities missing this data.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from tools.ingest.garmin_worker import GarminIngestWorker

logger = logging.getLogger(__name__)


class ActivityDetailsFetcher:
    """Bulk fetch activity_details.json for all activities."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        delay_seconds: float = 1.0,
        force: bool = False,
    ):
        """
        Initialize fetcher.

        Args:
            raw_dir: Raw data directory (default: data/raw)
            delay_seconds: Delay between API calls (rate limit protection)
            force: Force re-fetch even if file exists
        """
        if raw_dir is None:
            raw_dir = Path("data/raw")
        self.raw_dir = Path(raw_dir)
        self.activity_dir = self.raw_dir / "activity"
        self.delay_seconds = delay_seconds
        self.force = force

    def scan_activities(self) -> list[tuple[int, Path]]:
        """
        Scan activity directories and find missing activity_details.json.

        Returns:
            List of (activity_id, activity_dir) tuples that need fetching
        """
        missing: list[tuple[int, Path]] = []

        if not self.activity_dir.exists():
            logger.warning(f"Activity directory not found: {self.activity_dir}")
            return missing

        for activity_path in self.activity_dir.iterdir():
            if not activity_path.is_dir():
                continue

            # Skip special directories
            if activity_path.name.startswith("."):
                continue

            # Check if activity.json exists (validate directory)
            activity_json = activity_path / "activity.json"
            if not activity_json.exists():
                logger.debug(f"Skipping {activity_path.name}: no activity.json")
                continue

            # Extract activity_id from directory name
            try:
                activity_id = int(activity_path.name)
            except ValueError:
                logger.debug(f"Skipping {activity_path.name}: invalid activity ID")
                continue

            # Check if activity_details.json exists
            details_file = activity_path / "activity_details.json"
            if details_file.exists() and not self.force:
                logger.debug(
                    f"Skipping {activity_id}: activity_details.json already exists"
                )
                continue

            missing.append((activity_id, activity_path))

        return missing

    def fetch_single_activity(
        self,
        activity_id: int,
        activity_dir: Path,
    ) -> dict[str, Any]:
        """
        Fetch activity_details.json for a single activity.

        Args:
            activity_id: Activity ID
            activity_dir: Activity directory path

        Returns:
            Result dict with status ('success', 'skipped', 'error')
        """
        details_file = activity_dir / "activity_details.json"

        # Skip if file exists and force=False
        if details_file.exists() and not self.force:
            logger.info(f"Skipping {activity_id}: file already exists")
            return {
                "status": "skipped",
                "activity_id": activity_id,
            }

        try:
            # Fetch from API
            client = GarminIngestWorker.get_garmin_client()
            activity_data = client.get_activity_details(activity_id, maxchart=2000)

            # Save to file
            with open(details_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Successfully fetched activity_details for {activity_id}")
            return {
                "status": "success",
                "activity_id": activity_id,
            }

        except Exception as e:
            logger.error(f"Error fetching activity_details for {activity_id}: {e}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "error": str(e),
            }

    def fetch_all(self) -> dict[str, Any]:
        """
        Fetch all missing activity_details.json files.

        Returns:
            Summary dict with success/skip/error counts and details
        """
        # Scan for missing files
        missing = self.scan_activities()

        if not missing:
            logger.info("No missing activity_details.json files found")
            return {
                "total": 0,
                "success": 0,
                "skipped": 0,
                "error": 0,
                "errors": [],
            }

        logger.info(f"Found {len(missing)} activities to fetch")

        # Initialize counters
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        # Fetch with progress bar
        for activity_id, activity_dir in tqdm(
            missing, desc="Fetching activity details"
        ):
            result = self.fetch_single_activity(activity_id, activity_dir)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
                skip_count += 1
            elif result["status"] == "error":
                error_count += 1
                errors.append(result)

            # Rate limit protection
            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)

        # Generate summary
        summary = {
            "total": len(missing),
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
        python tools/bulk_fetch_activity_details.py [--force] [--delay 1.5]

    Options:
        --force: Force re-fetch even if file exists
        --delay: Delay between API calls in seconds (default: 1.0)
        --dry-run: Show what would be fetched without actually fetching
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Bulk fetch activity_details.json for all activities"
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

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create fetcher
    fetcher = ActivityDetailsFetcher(
        delay_seconds=args.delay,
        force=args.force,
    )

    if args.dry_run:
        # Dry run: scan and show what would be fetched
        missing = fetcher.scan_activities()
        print(f"Found {len(missing)} activities to fetch:")
        for activity_id, activity_dir in missing:
            print(f"  - Activity {activity_id} ({activity_dir})")
        return

    # Execute fetch
    summary = fetcher.fetch_all()

    # Display summary
    print("\n=== Fetch Summary ===")
    print(f"Total activities: {summary['total']}")
    print(f"Success: {summary['success']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Errors: {summary['error']}")

    if summary["errors"]:
        print("\n=== Error Details ===")
        for error in summary["errors"]:
            print(f"  - Activity {error['activity_id']}: {error['error']}")


if __name__ == "__main__":
    main()
