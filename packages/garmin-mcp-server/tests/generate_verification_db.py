"""Generate verification DuckDB from fixture JSON files.

Uses the same code path as production (GarminDBWriter + DuckDBSaver.save_data)
to ensure schema and data consistency. Does NOT require API authentication.

Usage:
    python tests/generate_verification_db.py [--output PATH]

Default output: tests/fixtures/verification.duckdb
"""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Fixture constants
FIXTURE_ACTIVITY_ID = 12345678901
FIXTURE_ACTIVITY_DATE = "2025-01-15"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
RAW_DIR = FIXTURES_DIR / "data" / "raw"
DEFAULT_OUTPUT = FIXTURES_DIR / "verification.duckdb"


def generate_verification_db(output_path: Path | None = None) -> Path:
    """Generate a verification DuckDB from fixture JSON files.

    Steps:
    1. Initialize schema via GarminDBWriter (same DDL as production)
    2. Insert data via DuckDBSaver.save_data (same code path as production)

    Args:
        output_path: Path for the output DuckDB file.
            Defaults to tests/fixtures/verification.duckdb.

    Returns:
        Path to the generated DuckDB file.
    """
    from garmin_mcp.database.db_writer import GarminDBWriter
    from garmin_mcp.ingest.duckdb_saver import save_data

    db_path = output_path or DEFAULT_OUTPUT

    # Remove existing DB to start fresh
    if db_path.exists():
        db_path.unlink()

    wal_path = db_path.with_suffix(".duckdb.wal")
    if wal_path.exists():
        wal_path.unlink()

    # Step 1: Initialize schema (creates all 15 tables + runs migrations)
    GarminDBWriter(db_path=str(db_path))

    # Step 2: Insert fixture data via production code path
    save_data(
        activity_id=FIXTURE_ACTIVITY_ID,
        raw_data={},  # Not used by save_data; it reads from raw_dir files
        db_path=str(db_path),
        raw_dir=RAW_DIR,
        activity_date=FIXTURE_ACTIVITY_DATE,
    )

    logger.info(f"Generated verification DB at {db_path}")
    return db_path


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate verification DuckDB from fixture data"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    try:
        result_path = generate_verification_db(args.output)
        print(f"OK: {result_path}")
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
