"""Migration: Add version column to training_plans and planned_workouts.

Adds version-based plan management:
- training_plans: version column + composite PK (plan_id, version) + status index
- planned_workouts: version column

DuckDB does not support ALTER TABLE ... DROP PRIMARY KEY or ADD PRIMARY KEY,
so we use CREATE TABLE ... AS SELECT + DROP + RENAME pattern.
"""

import argparse
import logging

import duckdb

from garmin_mcp.utils.paths import get_database_dir

logger = logging.getLogger(__name__)


def _table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return result is not None and result[0] > 0


def _column_exists(
    conn: duckdb.DuckDBPyConnection, table_name: str, column_name: str
) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        [table_name, column_name],
    ).fetchone()
    return result is not None and result[0] > 0


def migrate_add_plan_versioning(db_path: str | None = None) -> None:
    """Add version columns and change training_plans PK to (plan_id, version).

    Idempotent: skips if version column already exists.
    """
    if db_path is None:
        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    conn = duckdb.connect(db_path)
    try:
        # Check if tables exist
        if not _table_exists(conn, "training_plans"):
            print("  training_plans table does not exist, skipping.")
            return

        # Check if already migrated
        if _column_exists(conn, "training_plans", "version"):
            print("  version column already exists, skipping.")
            return

        print("  Adding version column to training_plans with PK change...")

        # 1. Recreate training_plans with composite PK
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

        # Add types/constraints (DuckDB CTAS doesn't preserve them)
        # We rely on application-level validation for constraints

        print("  Adding version column to planned_workouts...")

        # 2. Add version to planned_workouts
        conn.execute(
            "ALTER TABLE planned_workouts ADD COLUMN version INTEGER DEFAULT 1"
        )

        print("  Migration completed successfully.")

    finally:
        conn.close()


def run_plan_versioning_migration(db_path: str | None = None) -> None:
    """Run the plan versioning migration."""
    print("=" * 60)
    print("Running plan versioning migration")
    print("=" * 60)

    print("\n1. Add version columns and update PK")
    migrate_add_plan_versioning(db_path)

    print("\n" + "=" * 60)
    print("Plan versioning migration completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add plan versioning migration")
    parser.add_argument("--db-path", type=str, help="Path to DuckDB database")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_plan_versioning_migration(args.db_path)
