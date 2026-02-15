"""DuckDB data saver for activity data.

Orchestrates insertion into DuckDB tables with transaction batching.
Respects foreign key order: activities (parent) → child tables.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def should_insert_table(table_name: str, tables: list[str] | None) -> bool:
    """Check if a table should be inserted into DuckDB.

    Args:
        table_name: Name of the table to check
        tables: List of tables to insert (None = insert all)

    Returns:
        True if the table should be inserted, False otherwise
    """
    if tables is None:
        return True
    return table_name in tables


def save_data(
    activity_id: int,
    raw_data: dict[str, Any],
    db_path: str,
    raw_dir: Path,
    activity_date: str | None = None,
    tables: list[str] | None = None,
    base_weight_kg: float | None = None,
) -> dict[str, Any]:
    """Save all processed data to DuckDB.

    DuckDB insertion order (foreign key constraints):
    1. activities (parent table)
    2. splits, form_efficiency, heart_rate_zones, etc. (child tables)
    3. time_series_metrics (child table, optional)

    Single connection with explicit transaction batching.

    Args:
        activity_id: Activity ID
        raw_data: Raw data dict
        db_path: Path to DuckDB database
        raw_dir: Base raw data directory
        activity_date: Activity date (YYYY-MM-DD format)
        tables: List of tables to insert. If None, all tables are inserted.
        base_weight_kg: 7-day median weight for W/kg calculation

    Returns:
        File paths dict
    """
    from garmin_mcp.database.connection import get_write_connection

    activity_dir = raw_dir / "activity" / str(activity_id)

    with get_write_connection(db_path) as conn:
        try:
            conn.execute("BEGIN TRANSACTION")

            # Initialize raw file paths
            raw_activity_file: Path | None = activity_dir / "activity.json"
            raw_weather_file: Path | None = activity_dir / "weather.json"
            raw_gear_file: Path | None = activity_dir / "gear.json"

            # STEP 1: Insert activities (parent table)
            if should_insert_table("activities", tables):
                _insert_activities(
                    conn,
                    activity_id,
                    activity_date,
                    raw_dir,
                    raw_activity_file,
                    raw_weather_file,
                    raw_gear_file,
                    base_weight_kg,
                )

            # STEP 2: Insert child tables
            raw_splits_file: Path | None = activity_dir / "splits.json"
            if raw_splits_file and not raw_splits_file.exists():
                raw_splits_file = None

            if should_insert_table("splits", tables):
                _insert_table(
                    "splits",
                    activity_id,
                    conn,
                    raw_splits_file=raw_splits_file,
                )

            if should_insert_table("form_efficiency", tables):
                _insert_table(
                    "form_efficiency",
                    activity_id,
                    conn,
                    raw_splits_file=raw_splits_file,
                )

            raw_hr_zones_file: Path | None = activity_dir / "hr_zones.json"
            if raw_hr_zones_file and not raw_hr_zones_file.exists():
                raw_hr_zones_file = None

            if should_insert_table("heart_rate_zones", tables):
                _insert_heart_rate_zones(activity_id, conn, raw_hr_zones_file)

            if should_insert_table("hr_efficiency", tables):
                _insert_hr_efficiency(
                    activity_id,
                    conn,
                    raw_hr_zones_file,
                    raw_activity_file,
                )

            if should_insert_table("performance_trends", tables):
                _insert_performance_trends(activity_id, conn, raw_splits_file)

            if should_insert_table("lactate_threshold", tables):
                _insert_lactate_threshold(activity_id, conn, activity_dir)

            if should_insert_table("vo2_max", tables):
                _insert_vo2_max(activity_id, conn, activity_dir)

            if should_insert_table("time_series_metrics", tables):
                _insert_time_series(activity_id, conn, activity_dir)

            conn.execute("COMMIT")

        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"Error saving data for activity {activity_id}: {e}")
            raise

    return {"raw_dir": str(activity_dir)}


def _insert_activities(
    conn: Any,
    activity_id: int,
    activity_date: str | None,
    raw_dir: Path,
    raw_activity_file: Path | None,
    raw_weather_file: Path | None,
    raw_gear_file: Path | None,
    base_weight_kg: float | None,
) -> None:
    """Insert activities (parent table)."""
    from garmin_mcp.database.inserters.activities import insert_activities

    # Fallback: check if using old structure
    if raw_activity_file and not raw_activity_file.exists():
        legacy_raw_file = raw_dir / f"{activity_id}_raw.json"
        if legacy_raw_file.exists():
            raw_activity_file = None
            raw_weather_file = None
            raw_gear_file = None
            logger.warning(f"Using legacy raw data format for activity {activity_id}")

    success = insert_activities(
        activity_id=activity_id,
        date=activity_date or "1970-01-01",
        conn=conn,
        raw_activity_file=(
            str(raw_activity_file)
            if raw_activity_file and raw_activity_file.exists()
            else None
        ),
        raw_weather_file=(
            str(raw_weather_file)
            if raw_weather_file and raw_weather_file.exists()
            else None
        ),
        raw_gear_file=(
            str(raw_gear_file) if raw_gear_file and raw_gear_file.exists() else None
        ),
        base_weight_kg=base_weight_kg,
    )
    if success:
        logger.info(f"Inserted activities to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert activities to DuckDB for activity {activity_id}"
        )


def _insert_table(
    table_name: str,
    activity_id: int,
    conn: Any,
    raw_splits_file: Path | None = None,
) -> None:
    """Insert splits or form_efficiency table."""
    if table_name == "splits":
        from garmin_mcp.database.inserters.splits import insert_splits

        success = insert_splits(
            activity_id=activity_id,
            conn=conn,
            raw_splits_file=str(raw_splits_file) if raw_splits_file else None,
        )
    elif table_name == "form_efficiency":
        from garmin_mcp.database.inserters.form_efficiency import (
            insert_form_efficiency,
        )

        success = insert_form_efficiency(
            activity_id=activity_id,
            conn=conn,
            raw_splits_file=str(raw_splits_file) if raw_splits_file else None,
        )
    else:
        logger.warning(f"Unknown table: {table_name}")
        return

    if success:
        logger.info(f"Inserted {table_name} to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert {table_name} to DuckDB for activity {activity_id}"
        )


def _insert_heart_rate_zones(
    activity_id: int,
    conn: Any,
    raw_hr_zones_file: Path | None,
) -> None:
    """Insert heart_rate_zones table."""
    from garmin_mcp.database.inserters.heart_rate_zones import (
        insert_heart_rate_zones,
    )

    success = insert_heart_rate_zones(
        activity_id=activity_id,
        conn=conn,
        raw_hr_zones_file=str(raw_hr_zones_file) if raw_hr_zones_file else None,
    )
    if success:
        logger.info(f"Inserted heart_rate_zones to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert heart_rate_zones to DuckDB for activity {activity_id}"
        )


def _insert_hr_efficiency(
    activity_id: int,
    conn: Any,
    raw_hr_zones_file: Path | None,
    raw_activity_file: Path | None,
) -> None:
    """Insert hr_efficiency table."""
    from garmin_mcp.database.inserters.hr_efficiency import insert_hr_efficiency

    success = insert_hr_efficiency(
        activity_id=activity_id,
        conn=conn,
        raw_hr_zones_file=str(raw_hr_zones_file) if raw_hr_zones_file else None,
        raw_activity_file=(
            str(raw_activity_file)
            if raw_activity_file and raw_activity_file.exists()
            else None
        ),
    )
    if success:
        logger.info(f"Inserted hr_efficiency to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert hr_efficiency to DuckDB for activity {activity_id}"
        )


def _insert_performance_trends(
    activity_id: int,
    conn: Any,
    raw_splits_file: Path | None,
) -> None:
    """Insert performance_trends table."""
    from garmin_mcp.database.inserters.performance_trends import (
        insert_performance_trends,
    )

    success = insert_performance_trends(
        activity_id=activity_id,
        conn=conn,
        raw_splits_file=str(raw_splits_file) if raw_splits_file else None,
    )
    if success:
        logger.info(f"Inserted performance_trends to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert performance_trends to DuckDB for activity {activity_id}"
        )


def _insert_lactate_threshold(
    activity_id: int,
    conn: Any,
    activity_dir: Path,
) -> None:
    """Insert lactate_threshold table."""
    from garmin_mcp.database.inserters.lactate_threshold import (
        insert_lactate_threshold,
    )

    raw_file: Path | None = activity_dir / "lactate_threshold.json"
    if raw_file and not raw_file.exists():
        raw_file = None

    success = insert_lactate_threshold(
        activity_id=activity_id,
        conn=conn,
        raw_lactate_threshold_file=str(raw_file) if raw_file else None,
    )
    if success:
        logger.info(f"Inserted lactate_threshold to DuckDB for activity {activity_id}")
    else:
        logger.warning(
            f"Failed to insert lactate_threshold to DuckDB for activity {activity_id}"
        )


def _insert_vo2_max(activity_id: int, conn: Any, activity_dir: Path) -> None:
    """Insert vo2_max table."""
    from garmin_mcp.database.inserters.vo2_max import insert_vo2_max

    raw_file: Path | None = activity_dir / "vo2_max.json"
    if raw_file and not raw_file.exists():
        raw_file = None

    success = insert_vo2_max(
        activity_id=activity_id,
        conn=conn,
        raw_vo2_max_file=str(raw_file) if raw_file else None,
    )
    if success:
        logger.info(f"Inserted vo2_max to DuckDB for activity {activity_id}")
    else:
        logger.warning(f"Failed to insert vo2_max to DuckDB for activity {activity_id}")


def _insert_time_series(activity_id: int, conn: Any, activity_dir: Path) -> None:
    """Insert time_series_metrics table."""
    from garmin_mcp.database.inserters.time_series_metrics import (
        insert_time_series_metrics,
    )

    activity_details_file = activity_dir / "activity_details.json"
    if activity_details_file.exists():
        success = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=activity_id,
            conn=conn,
        )
        if success:
            logger.info(
                f"Inserted time_series_metrics to DuckDB for activity {activity_id}"
            )
        else:
            logger.error(
                f"Failed to insert time_series_metrics to DuckDB for activity {activity_id}"
            )
    else:
        logger.warning(
            f"activity_details.json not found for activity {activity_id}, "
            "skipping time_series_metrics insertion"
        )
