"""Migration: Add pace-dependent cadence evaluation columns to form_evaluations.

Adds expected/delta/star/score/needs_improvement/evaluation_text columns for
cadence, mirroring the GCT/VO/VR structure. The legacy cadence_actual,
cadence_minimum and cadence_achieved columns are retained for backward
compatibility.
"""

from pathlib import Path

import duckdb

from garmin_mcp.database.connection import get_write_connection

CADENCE_COLUMNS: list[tuple[str, str]] = [
    ("cadence_expected", "DOUBLE"),
    ("cadence_delta_pct", "DOUBLE"),
    ("cadence_star_rating", "VARCHAR"),
    ("cadence_score", "DOUBLE"),
    ("cadence_needs_improvement", "BOOLEAN"),
    ("cadence_evaluation_text", "VARCHAR"),
]


def add_cadence_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Add pace-dependent cadence columns to form_evaluations (idempotent)."""
    for col_name, col_type in CADENCE_COLUMNS:
        conn.execute(
            f"ALTER TABLE form_evaluations "
            f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )


def migrate_cadence_schema(db_path: str | None = None) -> None:
    """Add pace-dependent cadence columns to form_evaluations table.

    Args:
        db_path: Path to DuckDB database. If None, uses
            GARMIN_DATA_DIR/database/garmin_performance.duckdb

    Raises:
        FileNotFoundError: If database file does not exist
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_default_db_path

        db_path = get_default_db_path()

    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with get_write_connection(db_path) as conn:
        add_cadence_columns(conn)
        print("✅ Cadence columns migration completed successfully")
        for col_name, col_type in CADENCE_COLUMNS:
            print(f"   - Added {col_name} ({col_type}) to form_evaluations")


if __name__ == "__main__":
    """Run migration on production database."""
    migrate_cadence_schema()
