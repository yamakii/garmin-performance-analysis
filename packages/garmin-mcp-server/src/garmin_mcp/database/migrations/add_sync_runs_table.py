"""Migration: Add the ``sync_runs`` table (scheduled-sync execution log).

Records one row per scheduled catch-up sync run (issue #712, parent #701). Each
run captures the requested domains, the ``catch_up_ingest`` result payload, and
an overall status (``success`` | ``partial`` | ``error``) so that unattended
cron / systemd-timer runs leave an auditable trail of what was fetched and
whether any domain failed.

Idempotent: ``CREATE SEQUENCE`` / ``CREATE TABLE IF NOT EXISTS`` are no-ops when
the sequence/table already exist. ``run_id`` surrogate keys are drawn from
``seq_sync_runs_id`` via ``nextval``, mirroring the ``seq_athlete_goals_id``
pattern. DDL for this table is owned exclusively by the migration (not
``_ensure_tables()``) to keep a single source of truth (issue #342).
"""

import duckdb


def add_sync_runs_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``sync_runs`` table and its ``run_id`` sequence (idempotent)."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_sync_runs_id START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_runs (
            run_id INTEGER PRIMARY KEY,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            domains VARCHAR NOT NULL,
            results VARCHAR,
            status VARCHAR NOT NULL
        )
    """)
