"""Migration: Add the daily_wellness table.

Stores per-day physiological / recovery metrics (resting HR, overnight HRV +
status + baseline band, sleep duration + score, training readiness, body
battery high/low, average stress). Keyed by date via a UNIQUE index so cache
backfill and repeated ingestion behave as a day-level upsert.

Idempotent: ``CREATE TABLE IF NOT EXISTS`` / ``CREATE UNIQUE INDEX IF NOT
EXISTS`` are no-ops when the table/index already exist (e.g. on databases
created after the table was added to the table-creation path in
``_ensure_tables``).
"""

import duckdb


def add_daily_wellness_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the daily_wellness table and its date-unique index.

    Idempotent: safe to run when the table/index already exist.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_wellness (
            wellness_id INTEGER PRIMARY KEY,
            date DATE NOT NULL,
            resting_hr INTEGER,
            hrv_overnight_ms DOUBLE,
            hrv_status VARCHAR,
            hrv_baseline_low DOUBLE,
            hrv_baseline_high DOUBLE,
            sleep_seconds INTEGER,
            sleep_score INTEGER,
            training_readiness INTEGER,
            body_battery_high INTEGER,
            body_battery_low INTEGER,
            stress_avg INTEGER,
            source VARCHAR
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_daily_wellness_date ON daily_wellness(date)"
    )
