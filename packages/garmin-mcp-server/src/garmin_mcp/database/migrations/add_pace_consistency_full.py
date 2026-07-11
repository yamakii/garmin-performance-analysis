"""Migration: Add pace_consistency_full column to performance_trends.

``pace_consistency`` is now computed over *representative* run laps only (GPS
fragment laps are excluded), so tiny trailing laps no longer inflate the CV.
``pace_consistency_full`` stores the raw CV over every run lap for transparency
(#852). Existing rows default to NULL until the activity is re-ingested.

The migration is idempotent: it guards on table/column existence and uses
``ADD COLUMN IF NOT EXISTS`` so it can be applied repeatedly without error.
"""

import duckdb


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return result is not None and result[0] > 0


def _column_exists(
    conn: duckdb.DuckDBPyConnection, table_name: str, column_name: str
) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        [table_name, column_name],
    ).fetchone()
    return result is not None and result[0] > 0


def add_pace_consistency_full(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``pace_consistency_full DOUBLE`` to performance_trends (idempotent)."""
    if not _table_exists(conn, "performance_trends"):
        return
    if _column_exists(conn, "performance_trends", "pace_consistency_full"):
        return
    conn.execute(
        "ALTER TABLE performance_trends "
        "ADD COLUMN IF NOT EXISTS pace_consistency_full DOUBLE"
    )
