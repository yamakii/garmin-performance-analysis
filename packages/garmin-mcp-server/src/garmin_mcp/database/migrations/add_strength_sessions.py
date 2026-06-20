"""Migration: Add the ``strength_sessions`` table.

Strength training (補強) sessions are persisted at *summary* granularity in a
dedicated table rather than mixed into ``activities``: strength_training has no
distance/pace and would pollute the run-centric aggregations that read
``activities`` (issue #450, parent #449).

The table mirrors the summary fields returned by Garmin's activity list plus a
``category_counts`` JSON map (e.g. ``{"CRUNCH": 4, "PLANK": 7}``) aggregated
from the activity's ACTIVE exercise sets.

The migration is idempotent: ``CREATE TABLE IF NOT EXISTS`` makes it safe to
apply repeatedly. The same DDL is duplicated in
``db_writer.py:_ensure_tables`` so a freshly-constructed ``GarminDBWriter``
already has the table (see [[ensure-tables-recreates-schema]]).
"""

import duckdb


def add_strength_sessions(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``strength_sessions`` table (idempotent)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strength_sessions (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            start_time_local TIMESTAMP,
            activity_name VARCHAR,
            active_duration_seconds INTEGER,
            elapsed_duration_seconds INTEGER,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            calories INTEGER,
            active_sets INTEGER,
            total_sets INTEGER,
            category_counts JSON,
            ingested_at TIMESTAMP
        )
    """)
