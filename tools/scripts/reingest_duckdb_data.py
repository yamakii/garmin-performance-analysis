"""
DuckDB Data Re-ingestion Script

Re-ingest all activities from data/raw/activity/ into DuckDB with new normalized schema.
"""

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reingest_all_activities(
    db_path: str | None = None,
    raw_activity_dir: str | None = None,
    delete_old_db: bool = True,
) -> dict[str, int | list[tuple[int, str]]]:
    """
    Re-ingest all activities from raw data into DuckDB.

    Args:
        db_path: Path to DuckDB database
        raw_activity_dir: Path to raw activity directory
        delete_old_db: Whether to delete old database before re-ingestion

    Returns:
        Summary dict with success/failure counts
    """
    from tools.ingest.garmin_worker import GarminIngestWorker
    from tools.utils.paths import get_default_db_path, get_raw_dir

    # Resolve default paths
    if db_path is None:
        db_path = get_default_db_path()
    if raw_activity_dir is None:
        raw_activity_dir = str(get_raw_dir() / "activity")

    # 1. Delete old database if requested
    db_file = Path(db_path)
    if delete_old_db and db_file.exists():
        db_file.unlink()
        logger.info(f"Deleted old database: {db_path}")

    # 2. Get all activity IDs from raw directory
    raw_dir = Path(raw_activity_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw activity directory not found: {raw_activity_dir}")

    activity_ids = sorted(
        [int(d.name) for d in raw_dir.iterdir() if d.is_dir() and d.name.isdigit()]
    )
    logger.info(f"Found {len(activity_ids)} activities to process")

    # 3. Get activity dates from raw activity.json
    activity_date_map: dict[int, str] = {}

    for activity_id in activity_ids:
        # Try to get date from raw activity.json
        activity_json = raw_dir / str(activity_id) / "activity.json"
        if activity_json.exists():
            import json

            with open(activity_json) as f:
                data = json.load(f)
                # Extract date from summaryDTO.startTimeLocal or summaryDTO.startTimeGMT
                summary = data.get("summaryDTO", {})
                start_time = summary.get("startTimeLocal") or summary.get(
                    "startTimeGMT"
                )
                if start_time:
                    # Format: "2025-10-09 15:30:00" or "2025-10-09T15:30:00"
                    date = start_time.split("T")[0].split(" ")[0]
                    activity_date_map[activity_id] = date

    logger.info(f"Mapped {len(activity_date_map)} activities to dates")

    # 4. Re-ingest each activity using GarminIngestWorker directly
    worker = GarminIngestWorker(db_path=db_path)
    results: dict[str, int | list[tuple[int, str]]] = {
        "success": 0,
        "failed": 0,
        "errors": [],
    }

    for activity_id in activity_ids:
        date = activity_date_map.get(activity_id)
        if not date:
            logger.warning(f"No date found for activity {activity_id}, skipping")
            results["failed"] = int(results["failed"]) + 1  # type: ignore
            results["errors"].append((activity_id, "No date found"))  # type: ignore
            continue

        try:
            logger.info(f"Processing activity {activity_id} ({date})")

            # Process activity directly (includes DuckDB insertion via save_data)
            ingest_result = worker.process_activity(activity_id, date)

            if ingest_result["status"] != "success":
                results["failed"] = int(results["failed"]) + 1  # type: ignore
                results["errors"].append(  # type: ignore
                    (
                        activity_id,
                        f"Ingestion failed: {ingest_result.get('error', 'Unknown')}",
                    )
                )
                logger.warning(f"⚠️ Activity {activity_id} ingestion failed")
                continue

            results["success"] = int(results["success"]) + 1  # type: ignore
            logger.info(f"✅ Activity {activity_id} processed successfully")

        except Exception as e:
            results["failed"] = int(results["failed"]) + 1  # type: ignore
            results["errors"].append((activity_id, str(e)))  # type: ignore
            logger.error(f"❌ Activity {activity_id} failed: {e}")

    # 5. Summary
    logger.info("\n" + "=" * 60)
    logger.info("Re-ingestion Summary:")
    logger.info(f"  Total activities: {len(activity_ids)}")
    logger.info(f"  Successful: {results['success']}")
    logger.info(f"  Failed: {results['failed']}")
    logger.info("=" * 60)

    if results["errors"]:
        logger.warning("\nFailed activities:")
        for activity_id, error in results["errors"]:  # type: ignore
            logger.warning(f"  {activity_id}: {error}")

    return results


def main():
    """Main entry point."""
    import argparse

    from tools.utils.paths import get_database_dir, get_raw_dir

    parser = argparse.ArgumentParser(
        description="Re-ingest DuckDB data from raw activities"
    )
    parser.add_argument(
        "--db-path",
        default=str(get_database_dir() / "garmin_performance.duckdb"),
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--raw-dir",
        default=str(get_raw_dir() / "activity"),
        help="Path to raw activity directory",
    )
    parser.add_argument(
        "--keep-old",
        action="store_true",
        help="Keep old database (don't delete before re-ingestion)",
    )

    args = parser.parse_args()

    results = reingest_all_activities(
        db_path=args.db_path,
        raw_activity_dir=args.raw_dir,
        delete_old_db=not args.keep_old,
    )

    # Exit with error if any activities failed
    failed_count = int(results["failed"])  # type: ignore
    if failed_count > 0:
        exit(1)


if __name__ == "__main__":
    main()
