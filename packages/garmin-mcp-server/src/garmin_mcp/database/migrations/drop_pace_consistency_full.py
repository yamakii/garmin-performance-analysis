"""Migration: Drop pace_consistency_full from performance_trends.

``pace_consistency_full`` was added in #852 as the raw pace CV over *every* run
lap, "for transparency" alongside the fragment-filtered ``pace_consistency``.
Because it includes sub-km GPS fragment laps, its value has no analytical
meaning: on 2026-09-03 a steady 4x1 km easy run read 3.74% (full) vs 1.4%
(representative), and the summary agent graded the run against the misleading
figure. The column is removed rather than fixed (#972) — a fragment-inclusive CV
is a trap, not a metric.

Migration 19 (``add_pace_consistency_full``) stays in the registry so historical
DBs replay the same sequence; this migration then drops the column again.

The migration is idempotent: it guards on table existence and uses
``DROP COLUMN IF EXISTS`` so it can be applied repeatedly without error.
"""

import duckdb


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return result is not None and result[0] > 0


def drop_pace_consistency_full(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop ``pace_consistency_full`` from performance_trends (idempotent)."""
    if not _table_exists(conn, "performance_trends"):
        return
    conn.execute(
        "ALTER TABLE performance_trends DROP COLUMN IF EXISTS pace_consistency_full"
    )
