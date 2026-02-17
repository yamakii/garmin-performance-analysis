"""
Cadence Column Cleanup Migration

Background:
  time_series_metrics has 5 redundant cadence columns:
  - cadence (single foot)
  - double_cadence (both feet) ← The correct one
  - cadence_single_foot (duplicate)
  - cadence_total (calculated)
  - fractional_cadence (precision detail)

Goal:
  Keep only one cadence column containing directDoubleCadence (both feet).

Changes:
  1. Rename double_cadence to cadence_new
  2. Drop old cadence columns
  3. Rename cadence_new to cadence

Usage:
  python -m garmin_mcp.scripts.migrate_cadence_cleanup.py [--db-path PATH] [--dry-run]
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import duckdb


def backup_database(db_path: Path) -> Path:
    """Create backup of database before migration."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}.duckdb"

    print(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    print("✓ Backup created")

    return backup_path


def verify_columns_exist(conn: duckdb.DuckDBPyConnection) -> bool:
    """Verify expected columns exist."""
    result = conn.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'time_series_metrics'
        AND column_name IN ('cadence', 'double_cadence', 'cadence_single_foot', 'cadence_total', 'fractional_cadence')
        ORDER BY column_name
    """).fetchall()

    columns = [row[0] for row in result]
    expected = [
        "cadence",
        "cadence_single_foot",
        "cadence_total",
        "double_cadence",
        "fractional_cadence",
    ]

    print(f"\nFound columns: {columns}")
    print(f"Expected columns: {expected}")

    if set(columns) != set(expected):
        print("\n❌ Column mismatch!")
        print(f"  Missing: {set(expected) - set(columns)}")
        print(f"  Extra: {set(columns) - set(expected)}")
        return False

    return True


def check_data_consistency(conn: duckdb.DuckDBPyConnection):
    """Check that double_cadence has data."""
    result = conn.execute("""
        SELECT
            COUNT(*) as total_rows,
            COUNT(double_cadence) as non_null_double_cadence,
            AVG(double_cadence) as avg_double_cadence,
            MIN(double_cadence) as min_double_cadence,
            MAX(double_cadence) as max_double_cadence
        FROM time_series_metrics
    """).fetchone()

    if result is None:
        print("\n❌ No data in time_series_metrics!")
        return False

    print("\nData consistency check:")
    print(f"  Total rows: {result[0]:,}")
    print(f"  Non-null double_cadence: {result[1]:,}")
    print(f"  Avg double_cadence: {result[2]:.1f}")
    print(f"  Min double_cadence: {result[3]:.1f}")
    print(f"  Max double_cadence: {result[4]:.1f}")

    if result[1] == 0:
        print("\n⚠️  Warning: double_cadence has no data!")
        return False

    return True


def perform_migration(conn: duckdb.DuckDBPyConnection, dry_run: bool = False):
    """Perform the cadence column cleanup migration using table recreation strategy."""

    # Strategy: Create new table with correct schema, copy data, drop old, rename new
    # This avoids ALTER TABLE dependency issues

    steps = [
        (
            "Create temporary table with new schema",
            """
         CREATE TABLE time_series_metrics_new AS
         SELECT
             activity_id,
             seq_no,
             timestamp_s,
             sum_moving_duration,
             sum_duration,
             sum_elapsed_duration,
             sum_distance,
             sum_accumulated_power,
             heart_rate,
             speed,
             grade_adjusted_speed,
             double_cadence AS cadence,  -- Rename here
             power,
             ground_contact_time,
             vertical_oscillation,
             vertical_ratio,
             stride_length,
             vertical_speed,
             elevation,
             air_temperature,
             latitude,
             longitude,
             available_stamina,
             potential_stamina,
             body_battery,
             performance_condition
         FROM time_series_metrics
         """,
        ),
        ("Drop old time_series_metrics table", "DROP TABLE time_series_metrics"),
        (
            "Rename new table to time_series_metrics",
            "ALTER TABLE time_series_metrics_new RENAME TO time_series_metrics",
        ),
    ]

    print(f"\n{'='*80}")
    print(f"Migration Steps ({'DRY RUN' if dry_run else 'EXECUTING'})")
    print(f"{'='*80}\n")

    for i, (description, sql) in enumerate(steps, 1):
        print(f"Step {i}: {description}")
        print(f"  SQL: {sql[:100]}{'...' if len(sql) > 100 else ''}")

        if not dry_run:
            try:
                conn.execute(sql)
                print("  ✓ Success")
            except Exception as e:
                print(f"  ❌ Failed: {e}")
                raise
        else:
            print("  (skipped - dry run)")

        print()

    if dry_run:
        print("✓ Dry run completed - no changes made")
    else:
        print("✓ Migration completed successfully")


def verify_migration(conn: duckdb.DuckDBPyConnection):
    """Verify migration succeeded."""
    # Check new schema
    result = conn.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'time_series_metrics'
        AND column_name LIKE '%cadence%'
        ORDER BY column_name
    """).fetchall()

    columns = [row[0] for row in result]

    print(f"\n{'='*80}")
    print("Post-Migration Verification")
    print(f"{'='*80}\n")
    print(f"Remaining cadence columns: {columns}")

    if columns == ["cadence"]:
        print("✓ Schema correct - only 'cadence' column remains")
    else:
        print(f"❌ Unexpected columns: {columns}")
        return False

    # Check data
    stats = conn.execute("""
        SELECT
            COUNT(*) as total_rows,
            COUNT(cadence) as non_null_cadence,
            AVG(cadence) as avg_cadence,
            MIN(cadence) as min_cadence,
            MAX(cadence) as max_cadence
        FROM time_series_metrics
    """).fetchone()

    if stats is None:
        print("\n❌ No data in time_series_metrics after migration!")
        return False

    print("\nData verification:")
    print(f"  Total rows: {stats[0]:,}")
    print(f"  Non-null cadence: {stats[1]:,}")
    print(f"  Avg cadence: {stats[2]:.1f}")
    print(f"  Min cadence: {stats[3]:.1f}")
    print(f"  Max cadence: {stats[4]:.1f}")

    avg_cadence: float = stats[2]
    # Verify values match expected range (both feet should be 160-200 typically)
    if not (160 <= avg_cadence <= 200):
        print(
            f"\n⚠️  Warning: Average cadence {avg_cadence:.1f} is outside expected range (160-200)"
        )
        print("  This might indicate migration used wrong source column")
        return False

    print("\n✓ Migration verified successfully")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate cadence columns in time_series_metrics"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(
            "/home/yamakii/garmin_data/data/database/garmin_performance.duckdb"
        ),
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip creating backup (not recommended)",
    )

    args = parser.parse_args()

    db_path = args.db_path

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return 1

    print(f"{'='*80}")
    print("Cadence Column Cleanup Migration")
    print(f"{'='*80}\n")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    print()

    # Create backup (unless skip or dry-run)
    backup_path = None
    if not args.dry_run and not args.skip_backup:
        backup_path = backup_database(db_path)

    # Connect to database
    conn = duckdb.connect(str(db_path))

    try:
        # Pre-migration checks
        print(f"\n{'='*80}")
        print("Pre-Migration Checks")
        print(f"{'='*80}")

        if not verify_columns_exist(conn):
            print("\n❌ Column verification failed - aborting")
            return 1

        if not check_data_consistency(conn):
            print("\n❌ Data consistency check failed - aborting")
            return 1

        print("\n✓ Pre-migration checks passed")

        # Perform migration
        perform_migration(conn, dry_run=args.dry_run)

        # Post-migration verification (only if not dry-run)
        if not args.dry_run and not verify_migration(conn):
            print("\n❌ Post-migration verification failed!")
            if backup_path:
                print(f"\nBackup available at: {backup_path}")
                print(f"To restore: cp {backup_path} {db_path}")
            return 1

        print(f"\n{'='*80}")
        print("Migration Summary")
        print(f"{'='*80}\n")

        if args.dry_run:
            print("✓ Dry run completed successfully")
            print("  Run without --dry-run to apply changes")
        else:
            print("✓ Migration completed successfully")
            if backup_path:
                print(f"  Backup: {backup_path}")

        print("\nNext steps:")
        print("  1. Update GarminDBWriter to use single cadence column")
        print("  2. Test with sample activity")

        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        if backup_path:
            print(f"\nBackup available at: {backup_path}")
            print(f"To restore: cp {backup_path} {db_path}")
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
