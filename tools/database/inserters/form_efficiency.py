"""
FormEfficiencyInserter - Insert form_efficiency_summary from performance.json to DuckDB

Inserts form efficiency statistics (GCT, VO, VR) into form_efficiency table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def insert_form_efficiency(
    performance_file: str,
    activity_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Insert form_efficiency_summary from performance.json into DuckDB form_efficiency table.

    Steps:
    1. Load performance.json
    2. Extract form_efficiency_summary
    3. Insert into form_efficiency table

    Args:
        performance_file: Path to performance.json
        activity_id: Activity ID
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

        # Extract form_efficiency_summary
        form_eff_summary = performance_data.get("form_efficiency_summary")
        if not form_eff_summary or not isinstance(form_eff_summary, dict):
            logger.error(f"No form_efficiency_summary found in {performance_file}")
            return False

        # Set default DB path
        if db_path is None:
            db_path = "data/database/garmin_performance.duckdb"

        # Connect to DuckDB
        conn = duckdb.connect(str(db_path))

        # Ensure form_efficiency table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS form_efficiency (
                activity_id BIGINT PRIMARY KEY,
                gct_average DOUBLE,
                gct_min DOUBLE,
                gct_max DOUBLE,
                gct_std DOUBLE,
                gct_variability DOUBLE,
                gct_rating VARCHAR,
                gct_evaluation VARCHAR,
                vo_average DOUBLE,
                vo_min DOUBLE,
                vo_max DOUBLE,
                vo_std DOUBLE,
                vo_trend VARCHAR,
                vo_rating VARCHAR,
                vo_evaluation VARCHAR,
                vr_average DOUBLE,
                vr_min DOUBLE,
                vr_max DOUBLE,
                vr_std DOUBLE,
                vr_rating VARCHAR,
                vr_evaluation VARCHAR
            )
            """
        )

        # Delete existing record for this activity (for re-insertion)
        conn.execute("DELETE FROM form_efficiency WHERE activity_id = ?", [activity_id])

        # Extract values from nested dicts
        gct_stats = form_eff_summary.get("gct_stats", {})
        vo_stats = form_eff_summary.get("vo_stats", {})
        vr_stats = form_eff_summary.get("vr_stats", {})

        # Calculate variability if data exists
        gct_avg = gct_stats.get("average")
        gct_std = gct_stats.get("std")
        gct_variability = (gct_std / gct_avg * 100) if gct_avg and gct_std else None

        # Insert form efficiency data
        conn.execute(
            """
            INSERT INTO form_efficiency (
                activity_id,
                gct_average, gct_min, gct_max, gct_std, gct_variability, gct_rating,
                vo_average, vo_min, vo_max, vo_std, vo_rating,
                vr_average, vr_min, vr_max, vr_std, vr_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                gct_stats.get("average"),
                gct_stats.get("min"),
                gct_stats.get("max"),
                gct_stats.get("std"),
                gct_variability,
                form_eff_summary.get("gct_rating"),
                vo_stats.get("average"),
                vo_stats.get("min"),
                vo_stats.get("max"),
                vo_stats.get("std"),
                form_eff_summary.get("vo_rating"),
                vr_stats.get("average"),
                vr_stats.get("min"),
                vr_stats.get("max"),
                vr_stats.get("std"),
                form_eff_summary.get("vr_rating"),
            ],
        )

        conn.close()

        logger.info(
            f"Successfully inserted form efficiency data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting form efficiency: {e}")
        return False
