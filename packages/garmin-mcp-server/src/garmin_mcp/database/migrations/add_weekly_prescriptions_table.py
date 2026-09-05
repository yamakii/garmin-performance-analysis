"""Migration: Add the structured weekly prescription table.

``weekly_prescriptions`` holds one row per prescribed session per day, produced
by the weekly review and consumed by the daily check-in, workout scheduling,
activity analysis and the monthly plan view.

Write semantics (implemented in ``database/inserters/plan.py``):

- rows are append-only per ``batch_id`` — one save = one batch, and the latest
  batch for a week is canonical, so re-prescribing a week never mutates the
  superseded rows;
- ``status`` and the Garmin / activity ids are the only mutable columns, updated
  in place by ``update_prescription_status`` and ``reconcile_prescriptions``.

The migration is idempotent: every statement uses ``IF NOT EXISTS``. Surrogate
keys (``prescription_id``) and batch ids come from DuckDB sequences.
"""

import duckdb


def add_weekly_prescriptions_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the weekly_prescriptions table and its sequences (idempotent)."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_weekly_prescriptions_id START 1")
    conn.execute(
        "CREATE SEQUENCE IF NOT EXISTS seq_weekly_prescription_batches START 1"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_prescriptions (
            prescription_id INTEGER PRIMARY KEY,
            batch_id INTEGER NOT NULL,
            user_id VARCHAR DEFAULT 'default',
            review_id INTEGER,
            week_start_date DATE NOT NULL,
            date DATE NOT NULL,
            session_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            target_minutes INTEGER,
            target_km DOUBLE,
            hr_low INTEGER,
            hr_high INTEGER,
            pace_low_s_per_km INTEGER,
            pace_high_s_per_km INTEGER,
            rationale VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'prescribed',
            garmin_workout_id BIGINT,
            garmin_schedule_id BIGINT,
            actual_activity_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
