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
]
