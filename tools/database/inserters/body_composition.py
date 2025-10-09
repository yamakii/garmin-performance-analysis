"""
BodyCompositionInserter - Insert weight raw data to DuckDB

Inserts body composition data from data/raw/weight/ into body_composition table.
"""

import json
import logging
from pathlib import Path

from tools.database.db_writer import GarminDBWriter

logger = logging.getLogger(__name__)


def insert_body_composition_data(
    raw_file: str,
    date: str,
    db_path: str | None = None,
) -> bool:
    """
    Insert body composition data from weight raw file into DuckDB.

    Args:
        raw_file: Path to data/raw/weight/YYYY-MM-DD.json
        date: Date in YYYY-MM-DD format
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load raw weight data
        raw_path = Path(raw_file)
        if not raw_path.exists():
            logger.error(f"Raw weight file not found: {raw_file}")
            return False

        with open(raw_path, encoding="utf-8") as f:
            weight_data = json.load(f)

        # Initialize DB writer
        writer = GarminDBWriter(db_path=db_path) if db_path else GarminDBWriter()

        # Insert body composition data
        success = writer.insert_body_composition(date=date, weight_data=weight_data)

        if not success:
            logger.error(f"Failed to insert body composition data for {date}")
            return False

        logger.info(f"Successfully inserted body composition data for {date}")
        return True

    except Exception as e:
        logger.error(f"Error inserting body composition data: {e}")
        return False


def main() -> None:
    """Main entry point for body composition inserter."""
    import sys

    if len(sys.argv) < 3:
        print(
            "Usage: python -m tools.database.inserters.body_composition <raw_file> <date>"
        )
        print(
            "Example: python -m tools.database.inserters.body_composition data/raw/weight/2025-10-03.json 2025-10-03"
        )
        sys.exit(1)

    raw_file = sys.argv[1]
    date = sys.argv[2]

    success = insert_body_composition_data(raw_file, date)

    if success:
        print(f"✅ Body composition data inserted for {date}")
    else:
        print(f"❌ Failed to insert body composition data for {date}")
        sys.exit(1)


if __name__ == "__main__":
    main()
