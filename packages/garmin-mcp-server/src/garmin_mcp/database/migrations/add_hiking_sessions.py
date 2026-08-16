"""Migration: Add the ``hiking_sessions`` table.

Hiking (山行) is persisted at *summary* granularity in a dedicated table rather
than mixed into ``activities``: a mountain hike carries distance and elevation
but its pace/HR profile is nothing like a run, so letting it into ``activities``
would distort every run-centric aggregation (ACWR, load trend, form baselines)
that reads that table (issue #921). This mirrors the ``strength_sessions``
design (issue #450).

Unlike strength, every field needed here is already present in Garmin's activity
list summary, so no per-activity detail call is made.

The migration is idempotent: ``CREATE TABLE IF NOT EXISTS`` makes it safe to
apply repeatedly. The same DDL is duplicated in
``db_writer.py:_ensure_tables`` so a freshly-constructed ``GarminDBWriter``
already has the table (see [[ensure-tables-recreates-schema]]).
"""

import duckdb


def add_hiking_sessions(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``hiking_sessions`` table (idempotent)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hiking_sessions (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            start_time_local TIMESTAMP,
            activity_name VARCHAR,
            duration_seconds INTEGER,
            elapsed_duration_seconds INTEGER,
            distance_km DOUBLE,
            elevation_gain_m DOUBLE,
            elevation_loss_m DOUBLE,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            calories INTEGER,
            ingested_at TIMESTAMP
        )
    """)
