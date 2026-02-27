"""
Fix temperature unit inconsistency in DuckDB.

Convert Fahrenheit values (stored before 2025-10-24) to Celsius.
Identifies anomalies using >40°C threshold (華氏の可能性が高い).
"""

import logging
from pathlib import Path

from garmin_mcp.database.connection import get_connection, get_write_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_temperature_units(db_path: str, dry_run: bool = True) -> None:
    """
    Fix temperature unit inconsistency in activities table.

    Args:
        db_path: Path to DuckDB database
        dry_run: If True, only print changes without updating
    """
    ctx = get_connection(db_path) if dry_run else get_write_connection(db_path)
    with ctx as conn:
        # Find activities with Fahrenheit values (>40°C is unrealistic)
        anomalies = conn.execute("""
            SELECT
                activity_id,
                activity_date,
                temp_celsius,
                activity_name,
                ROUND((temp_celsius - 32) * 5 / 9, 2) as corrected_celsius
            FROM activities
            WHERE temp_celsius > 40
            ORDER BY activity_date DESC
            """).fetchall()

        if not anomalies:
            logger.info("No temperature anomalies found. Database is clean.")
            return

        logger.info(f"Found {len(anomalies)} activities with Fahrenheit values:\n")

        for activity_id, date, temp_f, name, temp_c in anomalies:
            logger.info(
                f"  {date} ({activity_id}): {temp_f:.1f}°F → {temp_c:.1f}°C | {name}"
            )

        if dry_run:
            logger.info(f"\n[DRY RUN] Would update {len(anomalies)} activities.")
            logger.info("Run with --apply to actually update the database.")
            return

        # Apply corrections
        logger.info(f"\nApplying corrections to {len(anomalies)} activities...")

        conn.execute("""
            UPDATE activities
            SET temp_celsius = ROUND((temp_celsius - 32) * 5 / 9, 2)
            WHERE temp_celsius > 40
            """)

        logger.info("✅ Temperature units fixed successfully!")

        # Verify
        remaining_row = conn.execute(
            "SELECT COUNT(*) FROM activities WHERE temp_celsius > 40"
        ).fetchone()
        remaining = remaining_row[0] if remaining_row is not None else 0

        if remaining > 0:
            logger.warning(f"⚠️  {remaining} anomalies still remain. Check manually.")
        else:
            logger.info("✅ All anomalies resolved.")


if __name__ == "__main__":
    import argparse

    from garmin_mcp.utils.paths import get_default_db_path

    parser = argparse.ArgumentParser(
        description="Fix temperature unit inconsistency in DuckDB"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update the database (default: dry run)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to DuckDB database (default: GARMIN_DATA_DIR/database/garmin_performance.duckdb)",
    )

    args = parser.parse_args()

    db_path = args.db_path or str(get_default_db_path())

    if not Path(db_path).exists():
        logger.error(f"Database not found: {db_path}")
        exit(1)

    fix_temperature_units(db_path, dry_run=not args.apply)
