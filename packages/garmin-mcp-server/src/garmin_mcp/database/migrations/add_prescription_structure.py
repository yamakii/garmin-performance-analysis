"""Migration: Add the structure column to weekly_prescriptions (Issue #1401).

A prescription's workout is an ordered list of steps (warmup / run / recovery /
rest / cooldown and repeat groups, see
:mod:`garmin_mcp.analysis.workout_structure`). Storing it on the row lets the
registration, the judging and the bookend accounting all read one structure,
so what the watch was asked to do and what the run is judged against cannot
drift apart (Epic #1398).

``structure`` is JSON in a nullable ``VARCHAR`` (the same encoding as
``strides`` / ``allowances``). Rows written before this migration stay
``NULL`` and are synthesized from their columns by
:func:`~garmin_mcp.analysis.workout_structure.synthesize_structure`.

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


def migrate_add_prescription_structure(conn: duckdb.DuckDBPyConnection) -> None:
    """Add the ``structure VARCHAR`` (JSON step list) column."""
    if not _table_exists(conn, "weekly_prescriptions"):
        return
    if _column_exists(conn, "weekly_prescriptions", "structure"):
        return
    conn.execute(
        "ALTER TABLE weekly_prescriptions ADD COLUMN IF NOT EXISTS structure VARCHAR"
    )
