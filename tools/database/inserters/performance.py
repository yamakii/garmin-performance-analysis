"""
PerformanceDataInserter - Insert performance.json to DuckDB

Inserts performance data into two tables:
1. activities - Activity metadata
2. performance_data - Full performance metrics
"""

import json
import logging
from pathlib import Path

from tools.database.db_writer import GarminDBWriter

logger = logging.getLogger(__name__)


def insert_performance_data(
    performance_file: str,
    activity_id: int,
    activity_date: str,
    db_path: str | None = None,
) -> bool:
    """
    Insert performance.json into DuckDB.

    Steps:
    1. Load performance.json
    2. Insert activity metadata (activities table)
    3. Insert full performance data (performance_data table)

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
        activity_date: Activity date (YYYY-MM-DD)
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load performance.json
        performance_path = Path(performance_file)
        if not performance_path.exists():
            logger.error(f"Performance file not found: {performance_file}")
            return False

        with open(performance_path, encoding="utf-8") as f:
            performance_data = json.load(f)

        # Initialize DB writer
        writer = GarminDBWriter(db_path=db_path) if db_path else GarminDBWriter()

        # Extract basic metrics for activities table
        basic_metrics = performance_data.get("basic_metrics", {})

        # Insert activity metadata
        success = writer.insert_activity(
            activity_id=activity_id,
            activity_date=activity_date,
            distance_km=basic_metrics.get("distance_km"),
            duration_seconds=basic_metrics.get("duration_seconds"),
            avg_pace_seconds_per_km=basic_metrics.get("avg_pace_seconds_per_km"),
            avg_heart_rate=basic_metrics.get("avg_heart_rate"),
        )

        if not success:
            logger.error(f"Failed to insert activity metadata for {activity_id}")
            return False

        # Insert full performance data
        success = writer.insert_performance_data(
            activity_id=activity_id,
            activity_date=activity_date,
            performance_data=performance_data,
        )

        if not success:
            logger.error(f"Failed to insert performance data for {activity_id}")
            return False

        logger.info(
            f"Successfully inserted performance data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting performance data: {e}")
        return False
