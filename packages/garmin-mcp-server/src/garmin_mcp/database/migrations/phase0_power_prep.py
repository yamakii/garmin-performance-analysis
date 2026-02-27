"""Phase 0: Database preparation for power efficiency evaluation.

This migration:
1. Drops form_baselines table (replaced by form_baseline_history)
2. Adds body_mass_kg column to activities table
3. Populates body_mass_kg from body_composition table
"""

from garmin_mcp.database.connection import get_write_connection
from garmin_mcp.utils.paths import get_database_dir


def migrate_phase0_drop_form_baselines(db_path: str | None = None) -> None:
    """Drop form_baselines table.

    The form_baselines table is replaced by form_baseline_history
    which provides versioned baseline tracking.

    Args:
        db_path: Path to DuckDB database. If None, uses default path.
    """
    if db_path is None:
        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    with get_write_connection(db_path) as conn:
        # Check if table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]

        if "form_baselines" in table_names:
            print("Dropping form_baselines table...")
            conn.execute("DROP TABLE form_baselines")
            print("✓ form_baselines table dropped")
        else:
            print("✓ form_baselines table does not exist (already removed)")


def migrate_phase0_add_body_mass_kg(db_path: str | None = None) -> None:
    """Add body_mass_kg column to activities table.

    Args:
        db_path: Path to DuckDB database. If None, uses default path.
    """
    if db_path is None:
        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    with get_write_connection(db_path) as conn:
        # Check if column already exists
        schema = conn.execute("PRAGMA table_info(activities)").fetchall()
        column_names = [row[1] for row in schema]

        if "body_mass_kg" not in column_names:
            print("Adding body_mass_kg column to activities table...")
            conn.execute("ALTER TABLE activities ADD COLUMN body_mass_kg DOUBLE")
            print("✓ body_mass_kg column added")
        else:
            print("✓ body_mass_kg column already exists")


def migrate_phase0_populate_body_mass_kg(db_path: str | None = None) -> None:
    """Populate body_mass_kg from body_composition table.

    For each activity, find the nearest body_composition measurement
    by date and populate body_mass_kg.

    Args:
        db_path: Path to DuckDB database. If None, uses default path.
    """
    if db_path is None:
        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    with get_write_connection(db_path) as conn:
        # First, check if column exists
        schema = conn.execute("PRAGMA table_info(activities)").fetchall()
        column_names = [row[1] for row in schema]

        if "body_mass_kg" not in column_names:
            raise ValueError(
                "body_mass_kg column does not exist. Run migrate_phase0_add_body_mass_kg first."
            )

        print("Populating body_mass_kg from body_composition...")

        # Strategy: For each activity, find the most recent body_composition measurement
        # on or before the activity date
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

        # Check results
        total_result = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
        assert total_result is not None
        total = total_result[0]

        populated_result = conn.execute("""
            SELECT COUNT(*) FROM activities WHERE body_mass_kg IS NOT NULL
        """).fetchone()
        assert populated_result is not None
        populated = populated_result[0]

        missing_result = conn.execute("""
            SELECT COUNT(*) FROM activities WHERE body_mass_kg IS NULL
        """).fetchone()
        assert missing_result is not None
        missing = missing_result[0]

    print(f"✓ body_mass_kg populated: {populated}/{total} activities")
    if missing > 0:
        print(f"  Warning: {missing} activities still missing body_mass_kg")
        print("  (These activities may be before any body_composition measurements)")


def run_all_phase0_migrations(db_path: str | None = None) -> None:
    """Run all Phase 0 migrations in order.

    Args:
        db_path: Path to DuckDB database. If None, uses default path.
    """
    print("=" * 60)
    print("Running Phase 0 migrations for power efficiency evaluation")
    print("=" * 60)

    print("\n1. Drop form_baselines table")
    migrate_phase0_drop_form_baselines(db_path)

    print("\n2. Add body_mass_kg column to activities")
    migrate_phase0_add_body_mass_kg(db_path)

    print("\n3. Populate body_mass_kg from body_composition")
    migrate_phase0_populate_body_mass_kg(db_path)

    print("\n" + "=" * 60)
    print("Phase 0 migrations completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 0 database migrations")
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to DuckDB database (default: use GARMIN_DATA_DIR)",
    )
    parser.add_argument(
        "--step",
        type=str,
        choices=[
            "drop_form_baselines",
            "add_body_mass_kg",
            "populate_body_mass_kg",
            "all",
        ],
        default="all",
        help="Which migration step to run (default: all)",
    )

    args = parser.parse_args()

    if args.step == "all":
        run_all_phase0_migrations(args.db_path)
    elif args.step == "drop_form_baselines":
        migrate_phase0_drop_form_baselines(args.db_path)
    elif args.step == "add_body_mass_kg":
        migrate_phase0_add_body_mass_kg(args.db_path)
    elif args.step == "populate_body_mass_kg":
        migrate_phase0_populate_body_mass_kg(args.db_path)
