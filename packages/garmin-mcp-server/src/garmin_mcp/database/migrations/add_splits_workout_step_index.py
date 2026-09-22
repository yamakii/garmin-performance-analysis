"""Migration: Add the workout_step_index column to splits.

Garmin records the laps of an [MCP] run step as ``ACTIVE``, so ``intensityType``
cannot tell a 20 s stride from the easy jog around it. The raw lap field
``wktStepIndex`` can: every iteration of a repeat group reuses the same step
index. Storing it lets the splits inserter mark strides ``role_phase='stride'``
and their recoveries ``role_phase='recovery'`` (Issue #1296, Epic #1294).

The column is a nullable ``INTEGER``; laps recorded without a structured
workout stay ``NULL``. No backfill is needed: past runs had no stride steps.

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


def add_splits_workout_step_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``workout_step_index INTEGER`` (nullable) to splits."""
    if not _table_exists(conn, "splits"):
        return
    if _column_exists(conn, "splits", "workout_step_index"):
        return
    conn.execute(
        "ALTER TABLE splits ADD COLUMN IF NOT EXISTS workout_step_index INTEGER"
    )
