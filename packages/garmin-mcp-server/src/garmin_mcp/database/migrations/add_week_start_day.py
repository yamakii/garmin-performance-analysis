"""Migration: Add week_start_day column to athlete_profile.

Stores the athlete's preferred week start day (0=Monday … 6=Sunday, following
``datetime.date.weekday()``) on the single-row profile. Existing rows default to
0 (Monday), preserving the prior implicit behaviour.

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


def add_week_start_day(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``week_start_day INTEGER DEFAULT 0`` to athlete_profile (idempotent)."""
    if not _table_exists(conn, "athlete_profile"):
        return
    if _column_exists(conn, "athlete_profile", "week_start_day"):
        return
    conn.execute(
        "ALTER TABLE athlete_profile "
        "ADD COLUMN IF NOT EXISTS week_start_day INTEGER DEFAULT 0"
    )
