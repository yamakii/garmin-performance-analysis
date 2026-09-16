"""Migration: Add gear lifecycle columns to activities.

``gear.json`` already carries everything needed to judge when a shoe is worn
out -- the athlete's own replacement limit (``maximumMeters``), the in-service
date (``dateBegin``), and whether the pair has been retired
(``gearStatusName`` / ``dateEnd``) -- but none of it was ingested.

Like the identity columns from #1207 these are **snapshots taken when the
activity was ingested**, not current truth: one shoe's ``gearStatusName`` is
observed changing from ``active`` to ``retired`` across its own activities. A
reader therefore takes the value from the shoe's most recent activity row.
"""

from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_write_connection

GEAR_LIFECYCLE_COLUMNS: list[tuple[str, str]] = [
    ("gear_max_km", "DOUBLE"),
    ("gear_status", "VARCHAR"),
    ("gear_since_date", "DATE"),
    ("gear_retired_date", "DATE"),
]


def add_gear_lifecycle_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Add the gear lifecycle columns to activities (idempotent)."""
    for col_name, col_type in GEAR_LIFECYCLE_COLUMNS:
        conn.execute(
            f"ALTER TABLE activities ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )


def migrate_gear_lifecycle(db_path: str | None = None) -> None:
    """Add gear lifecycle columns to the activities table.

    Existing rows keep NULL for all four columns until the values are
    backfilled from the raw gear.json files.

    Args:
        db_path: Path to DuckDB database. If None, uses
            GARMIN_DATA_DIR/database/garmin_performance.duckdb

    Raises:
        FileNotFoundError: If database file does not exist
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with get_write_connection(db_path) as conn:
        add_gear_lifecycle_columns(conn)
        print("✅ Gear lifecycle columns migration completed successfully")
        for col_name, col_type in GEAR_LIFECYCLE_COLUMNS:
            print(f"   - Added {col_name} ({col_type}) to activities")


if __name__ == "__main__":
    """Run migration on production database."""
    migrate_gear_lifecycle()
