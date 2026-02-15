"""Phase 1 Database Migration: Add Power Efficiency Columns.

This migration adds power efficiency evaluation columns to:
1. form_baseline_history - Power model coefficients (power_a, power_b, power_rmse)
2. form_evaluations - Power efficiency metrics
"""

import duckdb


def get_db_path() -> str:
    """Get database path from environment."""
    from garmin_mcp.utils.paths import get_default_db_path

    return get_default_db_path()


def migrate_form_baseline_history(conn: duckdb.DuckDBPyConnection) -> None:
    """Add power model columns to form_baseline_history.

    Columns:
    - power_a: Intercept coefficient (speed = power_a + power_b * power_wkg)
    - power_b: Slope coefficient
    - power_rmse: Root Mean Square Error of the model
    """
    print("Adding power columns to form_baseline_history...")

    # Check if columns already exist
    columns = conn.execute("DESCRIBE form_baseline_history").fetchall()
    column_names = [col[0] for col in columns]

    if "power_a" not in column_names:
        conn.execute("ALTER TABLE form_baseline_history ADD COLUMN power_a FLOAT")
        print("  ✓ Added power_a column")
    else:
        print("  - power_a already exists")

    if "power_b" not in column_names:
        conn.execute("ALTER TABLE form_baseline_history ADD COLUMN power_b FLOAT")
        print("  ✓ Added power_b column")
    else:
        print("  - power_b already exists")

    if "power_rmse" not in column_names:
        conn.execute("ALTER TABLE form_baseline_history ADD COLUMN power_rmse FLOAT")
        print("  ✓ Added power_rmse column")
    else:
        print("  - power_rmse already exists")


def migrate_form_evaluations(conn: duckdb.DuckDBPyConnection) -> None:
    """Add power efficiency evaluation columns to form_evaluations.

    Columns:
    - power_avg_w: Average power in watts
    - power_wkg: Power per kg body weight (W/kg)
    - speed_actual_mps: Actual speed in m/s
    - speed_expected_mps: Expected speed from power model (m/s)
    - power_efficiency_score: (actual - expected) / expected
    - power_efficiency_rating: Star rating (★★★★★ to ★☆☆☆☆)
    - power_efficiency_needs_improvement: Boolean flag (score < -0.02)
    """
    print("Adding power efficiency columns to form_evaluations...")

    # Check if columns already exist
    columns = conn.execute("DESCRIBE form_evaluations").fetchall()
    column_names = [col[0] for col in columns]

    new_columns = [
        ("power_avg_w", "FLOAT"),
        ("power_wkg", "FLOAT"),
        ("speed_actual_mps", "FLOAT"),
        ("speed_expected_mps", "FLOAT"),
        ("power_efficiency_score", "FLOAT"),
        ("power_efficiency_rating", "VARCHAR"),
        ("power_efficiency_needs_improvement", "BOOLEAN"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in column_names:
            conn.execute(
                f"ALTER TABLE form_evaluations ADD COLUMN {col_name} {col_type}"
            )
            print(f"  ✓ Added {col_name} column ({col_type})")
        else:
            print(f"  - {col_name} already exists")


def run_migration(db_path: str | None = None) -> None:
    """Run Phase 1 migration.

    Args:
        db_path: Optional database path. If None, uses GARMIN_DATA_DIR.
    """
    if db_path is None:
        db_path = get_db_path()

    print(f"Starting Phase 1 migration: {db_path}")
    print("=" * 60)

    conn = duckdb.connect(db_path)

    try:
        # Migrate form_baseline_history
        migrate_form_baseline_history(conn)

        print()

        # Migrate form_evaluations
        migrate_form_evaluations(conn)

        print("=" * 60)
        print("✓ Migration completed successfully")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
