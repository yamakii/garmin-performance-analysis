"""Migration: Add the mesocycle plan ledger tables.

Adds the two tables that hold the mid-term (mesocycle) plan:

- ``training_blocks``: the block ledger (~10 rows per season). One row per
  block with phase, date range, purpose, quality density, weight mode, cutback
  rule and the long-run ladder (one entry per week, stored as JSON).
- ``training_block_versions``: append-only JSON snapshots of the whole block
  list. ``save_training_blocks`` replaces the canonical rows wholesale
  (洗い替え, same semantics as ``athlete_profile``), so every save also appends
  a snapshot here and prior versions stay recoverable.

These tables are not API-derived, so they are intentionally excluded from
``scripts/regenerate/validator.py:AVAILABLE_TABLES``.

The migration is idempotent: every statement uses ``IF NOT EXISTS`` so it can be
applied repeatedly without error. Surrogate keys are populated from DuckDB
sequences, mirroring the ``seq_athlete_goals_id`` pattern in
``add_athlete_tables.py``.
"""

import duckdb


def add_training_blocks_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the training block ledger tables and sequences (idempotent)."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_training_blocks_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_training_block_versions_id START 1")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_blocks (
            block_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            sequence INTEGER NOT NULL,
            phase VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            purpose VARCHAR,
            weight_mode VARCHAR,
            quality_sessions_per_week INTEGER,
            quality_types VARCHAR,
            long_run_ladder VARCHAR,
            cutback_rule VARCHAR,
            notes VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_block_versions (
            version_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            blocks_data VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
