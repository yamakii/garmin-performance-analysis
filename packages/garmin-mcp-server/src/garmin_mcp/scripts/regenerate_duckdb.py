"""Regenerate DuckDB from existing raw data files.

Regenerates DuckDB performance data from existing raw data WITHOUT API calls.
Supports selective table regeneration, date range/ID filtering, and dry-run mode.

Usage:
    python -m garmin_mcp.scripts.regenerate_duckdb --help
"""

import json
import logging
from pathlib import Path
from typing import Any

from tqdm import tqdm

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.ingest.garmin_worker import GarminIngestWorker
from garmin_mcp.scripts.regenerate.deletion_strategy import (
    delete_activity_records as _delete_activity_records,
)
from garmin_mcp.scripts.regenerate.deletion_strategy import (
    delete_table_all_records as _delete_table_all_records,
)
from garmin_mcp.scripts.regenerate.validator import (
    filter_tables as _filter_tables,
)
from garmin_mcp.scripts.regenerate.validator import (
    validate_table_dependencies as _validate_table_dependencies,
)
from garmin_mcp.utils.paths import get_database_dir, get_raw_dir

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
        if delete_old_db and tables:
            raise ValueError(
                "--delete-db cannot be used with --tables. "
                "Database file deletion is only allowed for full regeneration (all tables)."
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

        if self.delete_old_db and self.db_path.exists():
            logger.warning(f"Deleting existing DuckDB: {self.db_path}")
            self.db_path.unlink()

        if self.delete_old_db:
            from garmin_mcp.database.db_writer import GarminDBWriter

            logger.info("Initializing database tables...")
            GarminDBWriter(db_path=str(self.db_path))

        self.db_reader = GarminDBReader(str(self.db_path))

    def filter_tables(self, tables: list[str] | None) -> list[str]:
        """Filter and validate table list."""
        return _filter_tables(tables)

    def validate_table_dependencies(
        self,
        tables: list[str] | None,
        activity_ids: list[int],
    ) -> None:
        """Validate parent activities exist before regenerating child tables."""
        _validate_table_dependencies(tables, activity_ids, self.db_path)

    def get_all_activities_from_raw(self) -> list[tuple[int, str | None]]:
        """Scan raw data directory and get all activity IDs with dates."""
        activities: list[tuple[int, str | None]] = []

        if not self.activity_dir.exists():
            logger.warning(f"Activity directory not found: {self.activity_dir}")
            return activities

        for activity_path in self.activity_dir.iterdir():
            if not activity_path.is_dir() or activity_path.name.startswith("."):
                continue

            try:
                activity_id = int(activity_path.name)
            except ValueError:
                logger.debug(f"Skipping {activity_path.name}: invalid activity ID")
                continue

            activity_date = self._extract_activity_date(activity_path)
            activities.append((activity_id, activity_date))

        return activities

    def _extract_activity_date(self, activity_path: Path) -> str | None:
        """Extract activity date from activity.json."""
        activity_json = activity_path / "activity.json"
        if not activity_json.exists():
            return None

        try:
            with open(activity_json, encoding="utf-8") as f:
                data = json.load(f)
                summary = data.get("summaryDTO", {})
                if summary and "startTimeLocal" in summary:
                    return str(summary["startTimeLocal"]).split("T")[0]
                elif "startTimeLocal" in data:
                    return str(data["startTimeLocal"]).split(" ")[0]
                elif "beginTimestamp" in data:
                    return str(data["beginTimestamp"]).split("T")[0]
        except Exception as e:
            logger.debug(f"Could not read activity date from {activity_json}: {e}")
        return None

    def get_activities_by_date_range(
        self, start_date: str, end_date: str
    ) -> list[tuple[int, str]]:
        """Get activity IDs from DuckDB by date range."""
        with get_connection(self.db_reader.db_path) as conn:
            query = """
                SELECT activity_id, activity_date
                FROM activities
                WHERE activity_date BETWEEN ? AND ?
                ORDER BY activity_date
            """
            results = conn.execute(query, (start_date, end_date)).fetchall()
            return [(row[0], str(row[1])) for row in results]

    def check_duckdb_cache(self, activity_id: int) -> bool:
        """Check if activity data exists in DuckDB."""
        if not self.db_path.exists():
            return False

        try:
            with get_connection(self.db_reader.db_path) as conn:
                query = "SELECT COUNT(*) FROM activities WHERE activity_id = ?"
                result = conn.execute(query, (activity_id,)).fetchone()
                return result[0] > 0 if result else False
        except Exception:
            return False

    def check_raw_data_exists(self, activity_id: int) -> bool:
        """Check if raw data exists for activity."""
        return (self.activity_dir / str(activity_id)).exists()

    def delete_activity_records(self, activity_ids: list[int]) -> None:
        """Delete existing records for specified activities from filtered tables."""
        if not self.tables:
            return
        _delete_activity_records(activity_ids, self.tables, self.db_path)

    def delete_table_all_records(self, tables: list[str]) -> None:
        """Delete all records from specified tables."""
        _delete_table_all_records(tables, self.db_path)

    def regenerate_single_activity(
        self,
        activity_id: int,
        activity_date: str | None = None,
    ) -> dict[str, Any]:
        """Regenerate DuckDB data for a single activity from raw data."""
        import time

        start_time = time.time()

        if not self.check_raw_data_exists(activity_id):
            logger.warning(f"Raw data not found for activity {activity_id}")
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": "Raw data not found",
                "elapsed_time": 0.0,
            }

        # Check DuckDB cache with table-awareness
        if not self.delete_old_db:
            if self.tables is not None:
                cache_exists = self.check_duckdb_cache(activity_id)
                if cache_exists and not self.force:
                    elapsed = time.time() - start_time
                    logger.info(
                        f"⏭️  Skipping activity {activity_id}: existing in DuckDB (use --force to update)"
                    )
                    return {
                        "status": "skipped",
                        "activity_id": activity_id,
                        "activity_date": activity_date,
                        "reason": "existing_in_duckdb_no_force",
                        "elapsed_time": elapsed,
                    }
                elif not cache_exists:
                    logger.debug(
                        f"Activity {activity_id} not in DuckDB, will regenerate activities + {self.tables}"
                    )
            else:
                cache_exists = self.check_duckdb_cache(activity_id)
                if cache_exists:
                    elapsed = time.time() - start_time
                    logger.debug(
                        f"Skipping {activity_id}: DuckDB cache exists ({elapsed:.2f}s)"
                    )
                    return {
                        "status": "skipped",
                        "activity_id": activity_id,
                        "activity_date": activity_date,
                        "elapsed_time": elapsed,
                    }

        try:
            worker = GarminIngestWorker()
            result = worker.process_activity(
                activity_id,
                activity_date or "",
                tables=self.tables,
            )

            elapsed = time.time() - start_time
            tables_info = f" (tables: {', '.join(self.tables)})" if self.tables else ""
            logger.info(
                f"Processed activity {activity_id} in {elapsed:.2f}s{tables_info}"
            )
            return {
                "status": "success",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "files": result,
                "tables": self.tables,
                "elapsed_time": elapsed,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Error regenerating data for activity {activity_id} ({elapsed:.2f}s): {e}"
            )
            return {
                "status": "error",
                "activity_id": activity_id,
                "activity_date": activity_date,
                "error": str(e),
                "elapsed_time": elapsed,
            }

    def regenerate_all(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        activity_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Regenerate DuckDB data for multiple activities."""
        if activity_ids and (start_date or end_date):
            raise ValueError(
                "Cannot specify both activity_ids and date range. "
                "Use one or the other."
            )

        # Get activity list
        if activity_ids:
            all_activities_dict = {
                a[0]: a[1] for a in self.get_all_activities_from_raw()
            }
            activities: list[tuple[int, str | None]] = [
                (aid, all_activities_dict.get(aid)) for aid in activity_ids
            ]
            logger.info(f"Regenerating data for {len(activities)} specified activities")
        elif start_date and end_date:
            activities_from_db = self.get_activities_by_date_range(start_date, end_date)
            activities = list(activities_from_db)
            logger.info(
                f"Found {len(activities)} activities between {start_date} and {end_date}"
            )
        else:
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
                "tables": self.tables,
            }

        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        tables_info = (
            f" (tables: {', '.join(self.tables)})" if self.tables else " (all tables)"
        )
        logger.info(f"Regenerating{tables_info}")

        resolved_ids = [a[0] for a in activities]

        # Validate table dependencies before deletion
        if activity_ids or (start_date and end_date):
            self.validate_table_dependencies(self.tables, resolved_ids)

        # Deletion strategy based on activity_ids AND force flag
        if self.tables and self.force:
            if activity_ids:
                self.delete_activity_records(activity_ids)
            elif start_date and end_date:
                self.delete_activity_records(resolved_ids)
            else:
                self.delete_table_all_records(self.tables)
        elif self.tables and not self.force:
            tables_info_str = ", ".join(self.tables)
            logger.info(
                "ℹ️  Skipping deletion (existing records will be preserved)\n"
                f"   Tables: {tables_info_str}\n"
                "   Reason: --force flag not specified\n"
                "   To update existing records, add --force flag to your command"
            )

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

        summary = {
            "total": len(activities),
            "success": success_count,
            "skipped": skip_count,
            "error": error_count,
            "errors": errors,
            "tables": self.tables,
        }

        logger.info(
            f"Regeneration completed{tables_info}: {success_count} success, "
            f"{skip_count} skipped, {error_count} errors"
        )

        return summary


def main():
    """CLI entry point for DuckDB regeneration."""
    import argparse

    from garmin_mcp.scripts.regenerate.validator import AVAILABLE_TABLES

    parser = argparse.ArgumentParser(
        description="Regenerate DuckDB from existing raw data files (NO API calls)"
    )
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--activity-ids",
        type=int,
        nargs="+",
        help="List of activity IDs",
    )
    parser.add_argument(
        "--tables",
        type=str,
        nargs="+",
        choices=AVAILABLE_TABLES,
        help="List of tables to regenerate (default: all tables)",
    )
    parser.add_argument(
        "--delete-db",
        action="store_true",
        help="Delete existing DuckDB before regeneration (complete reset)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update by deleting existing records before re-insertion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be regenerated without actually regenerating",
    )

    args = parser.parse_args()

    if args.activity_ids and (args.start_date or args.end_date):
        parser.error("Cannot specify both --activity-ids and date range.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        regenerator = DuckDBRegenerator(
            delete_old_db=args.delete_db,
            tables=args.tables,
            force=args.force,
        )
    except ValueError as e:
        parser.error(str(e))

    if args.dry_run:
        _run_dry_run(regenerator, args)
        return

    summary = regenerator.regenerate_all(
        start_date=args.start_date,
        end_date=args.end_date,
        activity_ids=args.activity_ids,
    )

    _print_summary(summary, args)


def _run_dry_run(regenerator: DuckDBRegenerator, args: Any) -> None:
    """Execute dry run mode."""
    from garmin_mcp.scripts.regenerate.validator import AVAILABLE_TABLES

    if args.activity_ids:
        activities: list[tuple[int, str | None]] = [
            (aid, None) for aid in args.activity_ids
        ]
    elif args.start_date and args.end_date:
        activities = list(
            regenerator.get_activities_by_date_range(args.start_date, args.end_date)
        )
    else:
        activities = regenerator.get_all_activities_from_raw()

    print("\n=== Dry Run ===")
    print(f"Delete old DuckDB: {args.delete_db}")
    print(f"Force update: {args.force}")
    if args.tables and not args.force:
        print("⚠️  Warning: Without --force, existing records will be skipped")

    if args.tables:
        print(f"Tables to regenerate: {', '.join(args.tables)}")
        skipped = [t for t in AVAILABLE_TABLES if t not in args.tables]
        if skipped:
            print(f"  → {len(skipped)} table(s) will be skipped: {', '.join(skipped)}")
    else:
        print(f"Tables to regenerate: all ({len(AVAILABLE_TABLES)} tables)")

    print(f"\nFound {len(activities)} activities:")

    for activity_id, activity_date in activities[:10]:
        raw_exists = regenerator.check_raw_data_exists(activity_id)
        cache_exists = regenerator.check_duckdb_cache(activity_id)

        if not raw_exists:
            status = "❌ No raw data"
        elif cache_exists and not args.delete_db:
            status = "⏭️  Skip (cache exists)"
        else:
            status = "✅ Will regenerate"

        date_str = f" ({activity_date})" if activity_date else ""
        print(f"  - Activity {activity_id}{date_str}: {status}")

    if len(activities) > 10:
        print(f"  ... and {len(activities) - 10} more")


def _print_summary(summary: dict[str, Any], args: Any) -> None:
    """Print regeneration summary."""
    print("\n=== Regeneration Summary ===")
    print(f"Total activities: {summary['total']}")
    print(f"Success: {summary['success']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Errors: {summary['error']}")

    if summary.get("tables"):
        print(f"\nTables regenerated: {', '.join(summary['tables'])}")
    else:
        print("\nTables regenerated: all (11 tables)")

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
