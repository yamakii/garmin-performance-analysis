"""Migration: Add the ``activity_context`` and ``coaching_rules`` tables.

Both tables hold athlete-specific knowledge that must stay in the local DB and
never enter the public repository's rules or code (issue #1520, Epic #1519).

``activity_context`` stores per-activity facts the athlete states in
conversation (a commute run, the load carried, strides carried over from the
previous day, why they walked, apparel or sensor mounting). It is append-only:
for each ``(activity_id, kind)`` the newest row wins on read.

``coaching_rules`` stores coaching rules that apply only to this athlete
(preferences, corrections, incident-derived reads). It is append-only too,
except that deactivating a rule sets ``active = false`` and ``deactivated_at``.

Both are athlete input that cannot be re-fetched from Garmin. The migration is
idempotent (``CREATE SEQUENCE / TABLE IF NOT EXISTS``). The same DDL is reused
by ``db_writer.py:_ensure_tables`` so a freshly-constructed ``GarminDBWriter``
already has both tables (the ``daily_energy`` convention).
"""

import duckdb

ACTIVITY_CONTEXT_SEQ_DDL = "CREATE SEQUENCE IF NOT EXISTS activity_context_seq START 1"

ACTIVITY_CONTEXT_DDL = """
    CREATE TABLE IF NOT EXISTS activity_context (
        context_id INTEGER PRIMARY KEY DEFAULT nextval('activity_context_seq'),
        user_id VARCHAR NOT NULL DEFAULT 'default',
        activity_id BIGINT NOT NULL,
        kind VARCHAR NOT NULL,
        value VARCHAR,
        load_kg DOUBLE,
        source VARCHAR NOT NULL DEFAULT 'athlete_stated',
        note VARCHAR,
        created_at TIMESTAMP DEFAULT current_timestamp
    )
"""

COACHING_RULES_SEQ_DDL = "CREATE SEQUENCE IF NOT EXISTS coaching_rules_seq START 1"

COACHING_RULES_DDL = """
    CREATE TABLE IF NOT EXISTS coaching_rules (
        rule_id INTEGER PRIMARY KEY DEFAULT nextval('coaching_rules_seq'),
        user_id VARCHAR NOT NULL DEFAULT 'default',
        scope VARCHAR NOT NULL,
        rule_text VARCHAR NOT NULL,
        rationale VARCHAR,
        origin_date DATE,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT current_timestamp,
        deactivated_at TIMESTAMP
    )
"""


def add_activity_context_and_coaching_rules(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Create ``activity_context`` and ``coaching_rules`` (idempotent)."""
    conn.execute(ACTIVITY_CONTEXT_SEQ_DDL)
    conn.execute(ACTIVITY_CONTEXT_DDL)
    conn.execute(COACHING_RULES_SEQ_DDL)
    conn.execute(COACHING_RULES_DDL)
