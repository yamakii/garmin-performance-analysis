"""Migration: Add the ``trend_analyses`` table (longitudinal trend narration).

Stores weekly / monthly longitudinal trend narratives (issue #789, parent #701,
spike #714). Append-only + latest-by-``created_at`` DESC, mirroring the
``weekly_reviews`` pattern: re-saving the same ``(user_id, granularity,
period_start)`` appends a new version rather than overwriting. One run = one row,
so no ``run_id`` column is needed (unlike ``section_analyses``).

Idempotent: ``CREATE SEQUENCE`` / ``CREATE TABLE IF NOT EXISTS`` are no-ops when
the sequence/table already exist. ``analysis_id`` surrogate keys are drawn from
``seq_trend_analyses_id`` via ``nextval``, mirroring the ``seq_sync_runs_id``
pattern. DDL for this table is owned exclusively by the migration (not
``_ensure_tables()``) to keep a single source of truth (issue #342).
"""

import duckdb


def add_trend_analyses_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the ``trend_analyses`` table and its sequence (idempotent)."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_trend_analyses_id START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_analyses (
            analysis_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            granularity VARCHAR NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            analysis_data VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            agent_name VARCHAR,
            agent_version VARCHAR
        )
    """)
