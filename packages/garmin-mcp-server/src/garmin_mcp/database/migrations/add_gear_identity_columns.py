"""Migration: Add gear identity columns (nickname + uuid) to activities.

Garmin's gear entry form changed: ``customMakeModel`` now holds only the base
model name, so two generations of the same shoe ("v15" and a future "v16")
share one string. The version now lives in the gear nickname
(``gear.json`` -> ``displayName``), and each pair carries a stable ``uuid``.

Storing both lets the analysis key shoe mileage on identity rather than on a
name that can collide, and lets it name the shoe the way the athlete does.
"""

from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_write_connection

GEAR_IDENTITY_COLUMNS: list[tuple[str, str]] = [
    ("gear_nickname", "VARCHAR"),
    ("gear_uuid", "VARCHAR"),
]


def add_gear_identity_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Add gear_nickname / gear_uuid to activities (idempotent)."""
    for col_name, col_type in GEAR_IDENTITY_COLUMNS:
        conn.execute(
            f"ALTER TABLE activities ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )


def migrate_gear_identity(db_path: str | None = None) -> None:
    """Add gear identity columns to the activities table.

    Existing rows keep NULL for both columns until the activities table is
    regenerated from the raw gear.json files.

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
        add_gear_identity_columns(conn)
        print("✅ Gear identity columns migration completed successfully")
        for col_name, col_type in GEAR_IDENTITY_COLUMNS:
            print(f"   - Added {col_name} ({col_type}) to activities")


if __name__ == "__main__":
    """Run migration on production database."""
    migrate_gear_identity()
