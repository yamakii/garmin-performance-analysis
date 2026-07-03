"""Migration: Drop the legacy unique index on section_analyses.

Earlier schema versions created ``idx_activity_section`` as a UNIQUE index on
``(activity_id, section_type)``, which forced a re-analysis to overwrite the
prior section result (``ON CONFLICT DO UPDATE``). Section analyses now append a
new version per run (the reader returns the latest version per section type as
canonical), so the unique index must be dropped to allow multiple rows per
``(activity_id, section_type)``.

The migration is idempotent: ``DROP INDEX IF EXISTS`` is a no-op when the index
is already absent (e.g. on databases created after the index was removed from
the table-creation path).
"""

import duckdb


def drop_section_analysis_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop the legacy unique index so multiple versions per section are allowed.

    Idempotent: safe to run when the index does not exist.
    """
    conn.execute("DROP INDEX IF EXISTS idx_activity_section")
