"""Migration: Add a unique index on body_composition(date).

Earlier schema versions allowed multiple ``body_composition`` rows per date,
so cache backfill (and repeated ingestion) could duplicate a single day. The
table is now the single source of truth for body composition and is keyed by
date, so a UNIQUE index on ``date`` is required to make ``INSERT OR REPLACE``
behave as a day-level upsert.

The migration is idempotent: ``CREATE UNIQUE INDEX IF NOT EXISTS`` is a no-op
when the index already exists (e.g. on databases created after the index was
added to the table-creation path).
"""

import duckdb


def add_body_composition_date_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the unique index so body_composition is keyed by date.

    Idempotent: safe to run when the index already exists.
    """
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_body_composition_date ON body_composition(date)"
    )
