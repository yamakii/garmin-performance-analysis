"""Migration: Drop the legacy unique index on weekly_reviews.

Earlier schema versions created ``idx_weekly_reviews_week`` as a UNIQUE index on
``(user_id, week_start_date)``, which forced same-week re-saves to overwrite the
prior review. Weekly reviews now append a new version per save (the reader
returns the latest version per week as canonical), so the unique index must be
dropped to allow multiple rows per week.

The migration is idempotent: ``DROP INDEX IF EXISTS`` is a no-op when the index
is already absent (e.g. on databases created after the index was removed from
the table-creation path).
"""

import duckdb


def drop_weekly_review_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop the legacy unique index so multiple versions per week are allowed.

    Idempotent: safe to run when the index does not exist.
    """
    conn.execute("DROP INDEX IF EXISTS idx_weekly_reviews_week")
