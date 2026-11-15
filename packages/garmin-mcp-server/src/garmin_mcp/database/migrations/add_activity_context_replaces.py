"""Migration: Add ``replaces_context_ids`` to ``activity_context`` (issue #1596).

Before this column the reader kept only the newest row per
``(activity_id, kind)``, so a second ``other`` row about the same run hid the
first. Kinds that can hold several facts now accumulate, and a row corrects or
merges earlier rows explicitly by listing their ``context_id`` here; the reader
hides every listed row. Rows stay append-only. Existing rows keep NULL.
"""

import duckdb

REPLACES_COLUMN_DDL = (
    "ALTER TABLE activity_context "
    "ADD COLUMN IF NOT EXISTS replaces_context_ids INTEGER[]"
)


def add_activity_context_replaces(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``replaces_context_ids`` to ``activity_context`` (idempotent).

    A database without ``activity_context`` is left alone; the table migration
    creates it with the column already in place.
    """
    exists = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_name = 'activity_context'"
    ).fetchone()
    if not exists or not exists[0]:
        return
    conn.execute(REPLACES_COLUMN_DDL)
