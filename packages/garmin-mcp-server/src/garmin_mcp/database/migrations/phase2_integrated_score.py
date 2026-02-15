"""Phase 2 migration: Add integrated_score and training_mode columns to form_evaluations."""

from pathlib import Path

import duckdb


def migrate_phase2_schema(db_path: str | None = None) -> None:
    """Add integrated_score and training_mode columns to form_evaluations table.

    Args:
        db_path: Path to DuckDB database. If None, uses GARMIN_DATA_DIR/database/garmin_performance.duckdb

    Raises:
        FileNotFoundError: If database file does not exist
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = duckdb.connect(db_path)

    try:
        # Add integrated_score column (DOUBLE)
        conn.execute("""
            ALTER TABLE form_evaluations
            ADD COLUMN IF NOT EXISTS integrated_score DOUBLE
        """)

        # Add training_mode column (VARCHAR)
        conn.execute("""
            ALTER TABLE form_evaluations
            ADD COLUMN IF NOT EXISTS training_mode VARCHAR
        """)

        print("✅ Phase 2 migration completed successfully")
        print("   - Added integrated_score (DOUBLE) to form_evaluations")
        print("   - Added training_mode (VARCHAR) to form_evaluations")

    finally:
        conn.close()


if __name__ == "__main__":
    """Run migration on production database."""
    migrate_phase2_schema()
