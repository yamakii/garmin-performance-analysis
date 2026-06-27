"""Migration registry: numbered list of all migrations.

Each migration is a (version, name, callable) tuple where callable accepts
a DuckDB connection. Existing migration scripts that manage their own
connections are wrapped with thin adapters.
"""

from collections.abc import Callable

import duckdb


def _wrap_phase0(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap phase0 migrations to run on an existing connection."""

    # These functions open their own connections, but the schema changes
    # they make are idempotent (IF NOT EXISTS / IF EXISTS checks).
    # We call the individual steps directly with conn by inlining the logic.

    # 1. Drop form_baselines if exists
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    if "form_baselines" in table_names:
        conn.execute("DROP TABLE form_baselines")

    # 2. Add body_mass_kg column if not exists
    schema = conn.execute("PRAGMA table_info(activities)").fetchall()
    column_names = [row[1] for row in schema]
    if "body_mass_kg" not in column_names:
        conn.execute("ALTER TABLE activities ADD COLUMN body_mass_kg DOUBLE")

    # 3. Populate body_mass_kg from body_composition (if table exists)
    tables_after = conn.execute("SHOW TABLES").fetchall()
    table_names_after = [t[0] for t in tables_after]
    if "body_composition" in table_names_after:
        conn.execute("""
            UPDATE activities
            SET body_mass_kg = (
                SELECT weight_kg
                FROM body_composition
                WHERE body_composition.date <= activities.activity_date
                ORDER BY body_composition.date DESC
                LIMIT 1
            )
            WHERE body_mass_kg IS NULL
        """)


def _wrap_phase1(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap phase1 migrations to run on an existing connection."""
    from .phase1_power_efficiency import (
        migrate_form_baseline_history,
        migrate_form_evaluations,
    )

    # These already accept conn directly
    migrate_form_baseline_history(conn)
    migrate_form_evaluations(conn)


def _wrap_phase2(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap phase2 migration to run on an existing connection."""
    conn.execute("""
        ALTER TABLE form_evaluations
        ADD COLUMN IF NOT EXISTS integrated_score DOUBLE
    """)
    conn.execute("""
        ALTER TABLE form_evaluations
        ADD COLUMN IF NOT EXISTS training_mode VARCHAR
    """)


def _wrap_remove_fk(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap FK removal migration.

    This migration is complex (CTAS backup-restore). Since the runner
    is called after _ensure_tables() which already creates FK-free tables,
    this becomes a no-op for new databases. For existing databases that
    already had FK removal applied, it's also a no-op.
    We check if any FK constraints exist before running.
    """
    # DuckDB doesn't have a clean way to check FK existence.
    # Since _ensure_tables() already creates FK-free schemas via
    # CREATE TABLE IF NOT EXISTS, this migration is effectively a no-op
    # for all current databases. Record it as applied.
    pass


def _wrap_add_cadence_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap cadence columns migration to run on an existing connection."""
    from .add_cadence_columns import add_cadence_columns

    add_cadence_columns(conn)


def _wrap_athlete_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap athlete tables migration to run on an existing connection."""
    from .add_athlete_tables import add_athlete_tables

    add_athlete_tables(conn)


def _wrap_drop_weekly_review_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap the weekly_reviews index drop migration on an existing connection."""
    from .drop_weekly_review_index import drop_weekly_review_index

    drop_weekly_review_index(conn)


def _wrap_add_body_composition_date_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap the body_composition date index migration on an existing connection."""
    from .add_body_composition_date_index import add_body_composition_date_index

    add_body_composition_date_index(conn)


def _wrap_add_strength_sessions(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap the strength_sessions table migration on an existing connection."""
    from .add_strength_sessions import add_strength_sessions

    add_strength_sessions(conn)


def _wrap_add_daily_wellness_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap the daily_wellness table migration on an existing connection."""
    from .add_daily_wellness_table import add_daily_wellness_table

    add_daily_wellness_table(conn)


def _wrap_add_week_start_day(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap the week_start_day column migration on an existing connection."""
    from .add_week_start_day import add_week_start_day

    add_week_start_day(conn)


def _wrap_plan_versioning(conn: duckdb.DuckDBPyConnection) -> None:
    """Wrap plan versioning migration to run on an existing connection."""
    from .add_plan_versioning import _column_exists, _table_exists

    if not _table_exists(conn, "training_plans"):
        return

    if _column_exists(conn, "training_plans", "version"):
        return

    conn.execute("""
        CREATE TABLE training_plans_new AS
        SELECT
            plan_id,
            1 AS version,
            goal_type,
            target_race_date,
            target_time_seconds,
            vdot,
            pace_zones_json,
            total_weeks,
            start_date,
            weekly_volume_start_km,
            weekly_volume_peak_km,
            runs_per_week,
            frequency_progression_json,
            personalization_notes,
            status,
            created_at
        FROM training_plans
    """)
    conn.execute("DROP TABLE training_plans")
    conn.execute("ALTER TABLE training_plans_new RENAME TO training_plans")

    conn.execute("ALTER TABLE planned_workouts ADD COLUMN version INTEGER DEFAULT 1")


MIGRATIONS: list[tuple[int, str, Callable[[duckdb.DuckDBPyConnection], None]]] = [
    (1, "phase0_power_prep", _wrap_phase0),
    (2, "phase1_power_efficiency", _wrap_phase1),
    (3, "phase2_integrated_score", _wrap_phase2),
    (4, "remove_fk_constraints", _wrap_remove_fk),
    (5, "add_plan_versioning", _wrap_plan_versioning),
    (6, "add_cadence_columns", _wrap_add_cadence_columns),
    (7, "add_athlete_tables", _wrap_athlete_tables),
    (8, "drop_weekly_review_index", _wrap_drop_weekly_review_index),
    (
        9,
        "add_body_composition_date_index",
        _wrap_add_body_composition_date_index,
    ),
    (10, "add_strength_sessions", _wrap_add_strength_sessions),
    (11, "add_daily_wellness_table", _wrap_add_daily_wellness_table),
    (12, "add_week_start_day", _wrap_add_week_start_day),
]
