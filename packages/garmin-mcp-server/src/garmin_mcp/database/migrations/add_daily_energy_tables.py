"""Migration: Add the ``daily_energy`` and ``intake_confirmations`` tables.

``daily_energy`` stores the daily user summary's intake (MyFitnessPal via
Garmin) and expenditure fields as facts, together with the metadata needed to
tell a partial or still-settling day from a real one: ``coverage_seconds``
(how much of the day the summary covers), the first and latest fetch times,
and how often the intake changed after the day had closed
(``post_close_revisions``) -- issue #1433, Epic #1432.

``intake_confirmations`` records the athlete's own confirmation that a day's
intake log is complete (or not). It is athlete input that cannot be
re-fetched from Garmin, so regenerating the DB from raw files loses it.

The migration is idempotent (``CREATE TABLE IF NOT EXISTS``). The same DDL is
duplicated in ``db_writer.py:_ensure_tables`` so a freshly-constructed
``GarminDBWriter`` already has both tables (the ``athlete_symptoms``
convention).
"""

import duckdb

DAILY_ENERGY_DDL = """
    CREATE TABLE IF NOT EXISTS daily_energy (
        date DATE PRIMARY KEY,
        consumed_kcal INTEGER,
        includes_consumed BOOLEAN,
        total_kcal INTEGER,
        active_kcal INTEGER,
        bmr_kcal INTEGER,
        coverage_seconds INTEGER,
        awake_seconds INTEGER,
        asleep_seconds INTEGER,
        total_steps INTEGER,
        fetched_at TIMESTAMP,
        first_fetched_at TIMESTAMP,
        post_close_revisions INTEGER,
        consumed_changed_at TIMESTAMP
    )
"""

INTAKE_CONFIRMATIONS_DDL = """
    CREATE TABLE IF NOT EXISTS intake_confirmations (
        user_id VARCHAR DEFAULT 'default',
        date DATE,
        status VARCHAR,
        note VARCHAR,
        confirmed_at TIMESTAMP,
        PRIMARY KEY (user_id, date)
    )
"""


def add_daily_energy_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create ``daily_energy`` and ``intake_confirmations`` (idempotent)."""
    conn.execute(DAILY_ENERGY_DDL)
    conn.execute(INTAKE_CONFIRMATIONS_DDL)
