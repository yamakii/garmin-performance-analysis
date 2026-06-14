"""Migration: Add athlete-centric tables for the weekly review cycle.

Adds four tables that form the foundation of the weekly training review cycle:
- athlete_profile: single-row profile holding the athlete's current focus
- athlete_goals: race goals with target times and priorities
- season_retrospectives: free-form season-level retrospectives
- weekly_reviews: per-week review records (UPSERT keyed on user_id + week_start)

These tables are not API-derived, so they are intentionally excluded from
``scripts/regenerate/validator.py:AVAILABLE_TABLES``.

The migration is idempotent: every statement uses ``IF NOT EXISTS`` so it can be
applied repeatedly without error. Surrogate keys (goal_id / retro_id /
review_id) are populated from DuckDB sequences, mirroring the
``seq_section_analyses_id`` pattern in ``db_writer.py``.
"""

import duckdb


def add_athlete_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create athlete-centric tables and their sequences (idempotent)."""
    # Sequences for surrogate primary keys
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_athlete_goals_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_season_retrospectives_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_weekly_reviews_id START 1")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS athlete_profile (
            user_id VARCHAR PRIMARY KEY DEFAULT 'default',
            current_focus VARCHAR,
            focus_notes VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS athlete_goals (
            goal_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            race_name VARCHAR NOT NULL,
            race_date DATE,
            priority VARCHAR,
            goal_type VARCHAR,
            distance_km DOUBLE,
            target_time_seconds INTEGER,
            status VARCHAR DEFAULT 'active',
            notes VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS season_retrospectives (
            retro_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            season_label VARCHAR,
            period_start DATE,
            period_end DATE,
            narrative VARCHAR,
            key_learnings VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_reviews (
            review_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            week_start_date DATE NOT NULL,
            week_end_date DATE NOT NULL,
            review_date DATE,
            review_data VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            agent_name VARCHAR,
            agent_version VARCHAR
        )
    """)

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_reviews_week
        ON weekly_reviews(user_id, week_start_date)
    """)
