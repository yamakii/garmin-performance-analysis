"""Migration: Add the rating column to weekly_prescriptions.

``rating`` carries the coach verdict of the prescribed session (``✅`` / ``🟡``
/ ``🔴``, nullable) that used to live only in the review prose
(``weekly_reviews.review_data.verdict``). With it, the per-day plan — session,
target, comment *and* verdict — lives in one store, so a mid-week revision can
no longer leave the review's copy stale (Issue #1021).

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


def add_prescription_rating(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``rating VARCHAR`` to weekly_prescriptions (idempotent, nullable)."""
    if not _table_exists(conn, "weekly_prescriptions"):
        return
    if _column_exists(conn, "weekly_prescriptions", "rating"):
        return
    conn.execute(
        "ALTER TABLE weekly_prescriptions ADD COLUMN IF NOT EXISTS rating VARCHAR"
    )
