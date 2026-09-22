"""Migration: Add the strides column to weekly_prescriptions.

Strides used to be a ``session_type`` of their own: a row with no jog body, no
intensity class and no target, registered as a 5x20s repeat group between a
warmup and a cooldown, and matched by the reconciler against any run of the day.
It was never used. Strides are a neuromuscular stimulus inside an easy run, so
they now live on the easy row as an optional structured add-on
``{"reps", "run_seconds", "recovery_seconds"}`` (Issue #1295), and the Garmin
workout places them between an opening easy segment and a final 5 minutes.

The add-on is stored as JSON in a nullable ``VARCHAR`` (the same encoding as
the ``training_blocks`` JSON columns); rows without strides stay ``NULL``.

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


def add_prescription_strides(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``strides VARCHAR`` (JSON, nullable) to weekly_prescriptions."""
    if not _table_exists(conn, "weekly_prescriptions"):
        return
    if _column_exists(conn, "weekly_prescriptions", "strides"):
        return
    conn.execute(
        "ALTER TABLE weekly_prescriptions ADD COLUMN IF NOT EXISTS strides VARCHAR"
    )
