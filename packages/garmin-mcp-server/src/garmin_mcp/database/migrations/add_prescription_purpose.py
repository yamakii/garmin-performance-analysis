"""Migration: Add the purpose and allowances columns to weekly_prescriptions.

``session_type`` says what kind of session a row is (easy / long / tempo ...),
but not what the run is *for*: a 2h long run may be an aerobic long run or a
goal-pace rehearsal, and the two are judged differently. ``purpose`` names that
finer intent (e.g. ``long_easy`` vs ``long_goal_pace``, Issue #1312), and
``allowances`` carries what the prescription explicitly permits, such as walk
breaks (``{"walk": true}``).

``purpose`` is a nullable ``VARCHAR``; ``allowances`` is JSON in a nullable
``VARCHAR`` (the same encoding as ``strides``). Rows written before this
migration stay ``NULL`` and fall back to the session-type default purpose.

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


def add_prescription_purpose(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``purpose VARCHAR`` and ``allowances VARCHAR`` (JSON) columns."""
    if not _table_exists(conn, "weekly_prescriptions"):
        return
    for column in ("purpose", "allowances"):
        if _column_exists(conn, "weekly_prescriptions", column):
            continue
        conn.execute(
            f"ALTER TABLE weekly_prescriptions ADD COLUMN IF NOT EXISTS {column} "
            "VARCHAR"
        )
