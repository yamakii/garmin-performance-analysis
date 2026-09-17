"""Migration: Add the ``athlete_symptoms`` table (pain & niggle log).

The athlete's own pain / tightness reports are the governor on long-run
progression, but nothing stored them: a stall like the March-2021 collapse
(43 -> 20 -> 9.6 -> 5.7 km/week) cannot be told apart from a planned cutback
after the fact. One row per (date, body_region) records what was felt, how bad,
and when (during the run / after it / next morning / on a rest day).

A ``severity`` of 0 is a *meaningful* row, not an absence: it records "asked and
clear", which is what lets a gate distinguish "no pain" from "never asked"
(issue #1220, Epic #1217).

The migration is idempotent: ``CREATE SEQUENCE / TABLE IF NOT EXISTS`` makes it
safe to apply repeatedly. The same DDL is duplicated in
``db_writer.py:_ensure_tables`` so a freshly-constructed ``GarminDBWriter``
already has the table (the ``strength_sessions`` / ``hiking_sessions``
convention).
"""

import duckdb


def add_athlete_symptoms(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``athlete_symptoms`` table and its sequence (idempotent)."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS athlete_symptoms_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS athlete_symptoms (
            symptom_id INTEGER PRIMARY KEY DEFAULT nextval('athlete_symptoms_seq'),
            user_id VARCHAR NOT NULL DEFAULT 'default',
            date DATE NOT NULL,
            body_region VARCHAR NOT NULL,
            side VARCHAR,
            severity INTEGER NOT NULL,
            phase VARCHAR NOT NULL,
            activity_id BIGINT,
            note VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """)
