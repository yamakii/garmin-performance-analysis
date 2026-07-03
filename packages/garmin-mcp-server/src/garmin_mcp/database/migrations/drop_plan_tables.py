"""Migration: Drop the self-authored plan tables (issue #788, parent #781).

The in-app training-plan *creation* feature and the plan-vs-actual comparison
were removed in Epic #781: the web endpoint (#786), analysis consumers (#785),
and the reader/inserter + MCP tools (#787) are all gone, and ``_ensure_tables()``
no longer creates these tables. This final migration drops the now-unused
``training_plans`` and ``planned_workouts`` tables.

Garmin-native scheduled workouts (``get_garmin_scheduled_workouts``) and the
weekly-review feedback against the Garmin-created plan are unaffected -- they
never used these tables.

Idempotent: ``DROP TABLE IF EXISTS`` is a no-op when the table is already
absent (fresh DBs never create them post-#787).
"""

import duckdb


def drop_plan_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop the training_plans and planned_workouts tables (idempotent)."""
    conn.execute("DROP TABLE IF EXISTS planned_workouts")
    conn.execute("DROP TABLE IF EXISTS training_plans")
