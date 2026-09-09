"""Migration: Add registered_bookend_minutes to weekly_prescriptions.

``reconcile_prescriptions`` widens a quality session's minutes band by the
warmup/cooldown its registered workout carries. That amount used to be the
constant :func:`~garmin_mcp.analysis.prescription_shape.bookend_minutes`
(10 + 5), which only matches the workout the standard builder produces. A
hand-built registration through ``schedule_custom_workout`` — the way a
buildup with a different HR zone per kilometre has to be written — can carry
different bookends (the 2026-09-09 tempo was registered with a 10-minute
cooldown, so 20 minutes rather than 15), leaving the band centred 5 minutes
short of what was actually asked for (Issue #1087).

This column records what was really registered so the reconciler can use it.
Rows registered before the column existed stay ``NULL`` and keep falling back
to the constant.

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


def add_prescription_registered_bookend_minutes(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Add ``registered_bookend_minutes INTEGER`` (idempotent, nullable)."""
    if not _table_exists(conn, "weekly_prescriptions"):
        return
    if _column_exists(conn, "weekly_prescriptions", "registered_bookend_minutes"):
        return
    conn.execute(
        "ALTER TABLE weekly_prescriptions "
        "ADD COLUMN IF NOT EXISTS registered_bookend_minutes INTEGER"
    )
