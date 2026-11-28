"""Migration: Add the dynamics_suspect flag to splits (issue #1635).

A pod whose GCT / vertical oscillation collapse mid-run (phone interference or a
loose mount) leaves splits that are measurement artifacts, not form. They are
kept, but flagged at ingest (``form_baseline.dynamics_quality``) so every form
path can drop them.

The column is ``BOOLEAN DEFAULT FALSE``; existing rows read FALSE until the
backfill script flags them. The migration is idempotent.
"""

import duckdb


def add_splits_dynamics_suspect(conn: duckdb.DuckDBPyConnection) -> None:
    """Add ``dynamics_suspect BOOLEAN DEFAULT FALSE`` to splits."""
    exists = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'splits'"
    ).fetchone()
    if not exists or exists[0] == 0:
        return
    conn.execute(
        "ALTER TABLE splits ADD COLUMN IF NOT EXISTS "
        "dynamics_suspect BOOLEAN DEFAULT FALSE"
    )
