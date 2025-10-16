"""
FormEfficiencyInserter - Insert form_efficiency_summary to DuckDB

Extracts form efficiency statistics (GCT, VO, VR) from raw data (splits.json)
and inserts into form_efficiency table.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def _calculate_rating(metric: str, value: float) -> str:
    """
    Calculate star rating for form metrics.

    Args:
        metric: Metric name ('gct', 'vo', 'vr')
        value: Metric value

    Returns:
        Star rating string (★★★★★ to ★☆☆☆☆)
    """
    # Rating thresholds based on garmin_worker.py line 892-910
    if metric == "gct":
        # Ground Contact Time (ms): lower is better
        if value < 220:
            return "★★★★★"
        elif value < 240:
            return "★★★★☆"
        elif value < 260:
            return "★★★☆☆"
        elif value < 280:
            return "★★☆☆☆"
        else:
            return "★☆☆☆☆"
    elif metric == "vo":
        # Vertical Oscillation (cm): lower is better
        if value < 6.5:
            return "★★★★★"
        elif value < 8.0:
            return "★★★★☆"
        elif value < 10.0:
            return "★★★☆☆"
        elif value < 12.0:
            return "★★☆☆☆"
        else:
            return "★☆☆☆☆"
    elif metric == "vr":
        # Vertical Ratio (%): lower is better
        if value < 7.0:
            return "★★★★★"
        elif value < 9.0:
            return "★★★★☆"
        elif value < 11.0:
            return "★★★☆☆"
        elif value < 13.0:
            return "★★☆☆☆"
        else:
            return "★☆☆☆☆"
    else:
        return "★★★☆☆"  # Default


def _extract_form_efficiency_from_raw(
    raw_splits_file: str | None = None,
    raw_activity_details_file: str | None = None,
) -> dict | None:
    """
    Extract form efficiency data from raw splits.json or activity_details.json.

    Priority: activity_details.json (second-by-second metrics) > splits.json (lap averages)

    Args:
        raw_splits_file: Path to splits.json
        raw_activity_details_file: Path to activity_details.json (optional)

    Returns:
        Dictionary with form_efficiency_summary data matching performance.json structure
    """
    import statistics

    # Try activity_details.json first (more granular data)
    if raw_activity_details_file:
        activity_details_path = Path(raw_activity_details_file)
        if activity_details_path.exists():
            # TODO: Implement activity_details.json parsing for metricsData
            # For now, fall through to splits.json
            pass

    # Fallback: Use splits.json
    if not raw_splits_file:
        logger.error("No raw data file provided for form efficiency extraction")
        return None

    splits_path = Path(raw_splits_file)
    if not splits_path.exists():
        logger.error(f"Splits file not found: {raw_splits_file}")
        return None

    with open(splits_path, encoding="utf-8") as f:
        splits_data = json.load(f)

    lap_dtos = splits_data.get("lapDTOs", [])
    if not lap_dtos:
        logger.error("No lapDTOs found in splits.json")
        return None

    # Extract form metrics from each lap
    gct_values = []
    vo_values = []
    vr_values = []

    for lap in lap_dtos:
        gct = lap.get("groundContactTime")
        vo = lap.get("verticalOscillation")
        vr = lap.get("verticalRatio")

        if gct is not None:
            gct_values.append(gct)
        if vo is not None:
            vo_values.append(vo)
        if vr is not None:
            vr_values.append(vr)

    # Calculate statistics
    if not (gct_values or vo_values or vr_values):
        logger.error("No form metrics found in splits.json")
        return None

    result: dict[str, dict[str, float] | str] = {}

    # GCT statistics
    if gct_values:
        gct_avg = statistics.mean(gct_values)
        result["gct_stats"] = {
            "average": gct_avg,
            "min": min(gct_values),
            "max": max(gct_values),
            "std": statistics.stdev(gct_values) if len(gct_values) > 1 else 0.0,
        }
        result["gct_rating"] = _calculate_rating("gct", gct_avg)

    # VO statistics
    if vo_values:
        vo_avg = statistics.mean(vo_values)
        result["vo_stats"] = {
            "average": vo_avg,
            "min": min(vo_values),
            "max": max(vo_values),
            "std": statistics.stdev(vo_values) if len(vo_values) > 1 else 0.0,
        }
        result["vo_rating"] = _calculate_rating("vo", vo_avg)

    # VR statistics
    if vr_values:
        vr_avg = statistics.mean(vr_values)
        result["vr_stats"] = {
            "average": vr_avg,
            "min": min(vr_values),
            "max": max(vr_values),
            "std": statistics.stdev(vr_values) if len(vr_values) > 1 else 0.0,
        }
        result["vr_rating"] = _calculate_rating("vr", vr_avg)

    return result


def insert_form_efficiency(
    activity_id: int,
    db_path: str | None = None,
    raw_splits_file: str | None = None,
    raw_activity_details_file: str | None = None,
) -> bool:
    """
    Insert form_efficiency_summary from raw data into DuckDB form_efficiency table.

    Steps:
    1. Load raw data files (splits.json or activity_details.json)
    2. Calculate form_efficiency_summary
    3. Insert into form_efficiency table

    Args:
        activity_id: Activity ID
        db_path: Optional DuckDB path (default: data/database/garmin_performance.duckdb)
        raw_splits_file: Path to splits.json (for raw mode)
        raw_activity_details_file: Path to activity_details.json (for raw mode, optional)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract from raw data
        form_eff_summary = _extract_form_efficiency_from_raw(
            raw_splits_file, raw_activity_details_file
        )
        # Check if extraction failed
        if not form_eff_summary:
            logger.error("Failed to extract form efficiency data from raw files")
            return False

        # Set default DB path
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

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
