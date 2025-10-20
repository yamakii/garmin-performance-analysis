"""
FormEfficiencyInserter - Insert form_efficiency_summary to DuckDB

Extracts form efficiency statistics (GCT, VO, VR) from raw data (splits.json)
and inserts into form_efficiency table.
"""

import json
import logging
from pathlib import Path
from typing import Any

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


def _calculate_gct_evaluation(avg_gct: float | None) -> str | None:
    """
    Evaluate ground contact time quality.

    Thresholds:
    - Optimal: 200-250ms
    - Good: 180-200ms or 250-280ms
    - Too short: <180ms (may indicate overstriding)
    - Too long: >280ms

    Args:
        avg_gct: Average ground contact time in ms

    Returns:
        GCT evaluation string or None

    Examples:
        >>> _calculate_gct_evaluation(220)
        'Excellent (220ms, optimal range)'
    """
    if avg_gct is None:
        return None

    gct_int = int(avg_gct)

    if 200 <= avg_gct <= 250:
        return f"Excellent ({gct_int}ms, optimal range)"
    elif 180 <= avg_gct < 200 or 250 < avg_gct <= 280:
        return f"Good ({gct_int}ms)"
    elif avg_gct < 180:
        return f"Too short ({gct_int}ms, may indicate overstriding)"
    else:  # >280
        return f"Too long ({gct_int}ms, target <250ms)"


def _calculate_vo_evaluation(avg_vo: float | None) -> str | None:
    """
    Evaluate vertical oscillation quality.

    Thresholds:
    - Excellent: <8cm (minimal bounce)
    - Good: 8-10cm
    - Acceptable: 10-12cm
    - Poor: >12cm (excessive vertical movement)

    Args:
        avg_vo: Average vertical oscillation in cm

    Returns:
        VO evaluation string or None

    Examples:
        >>> _calculate_vo_evaluation(8.2)
        'Good (8.2cm, target <8cm for optimal efficiency)'
    """
    if avg_vo is None:
        return None

    if avg_vo < 8:
        return f"Excellent ({avg_vo:.1f}cm, minimal bounce)"
    elif 8 <= avg_vo < 10:
        return f"Good ({avg_vo:.1f}cm, target <8cm for optimal efficiency)"
    elif 10 <= avg_vo < 12:
        return f"Acceptable ({avg_vo:.1f}cm, reduce bounce)"
    else:  # 12+
        return f"Poor ({avg_vo:.1f}cm, excessive vertical movement)"


def _calculate_vr_evaluation(avg_vr: float | None) -> str | None:
    """
    Evaluate vertical ratio quality.

    Thresholds:
    - Excellent: <6% (optimal efficiency)
    - Good: 6-8%
    - Acceptable: 8-10% (room for improvement)
    - Poor: >10% (high energy waste)

    Args:
        avg_vr: Average vertical ratio in %

    Returns:
        VR evaluation string or None

    Examples:
        >>> _calculate_vr_evaluation(6.8)
        'Good (6.8%)'
    """
    if avg_vr is None:
        return None

    if avg_vr < 6:
        return f"Excellent ({avg_vr:.1f}%, optimal efficiency)"
    elif 6 <= avg_vr < 8:
        return f"Good ({avg_vr:.1f}%)"
    elif 8 <= avg_vr < 10:
        return f"Acceptable ({avg_vr:.1f}%, room for improvement)"
    else:  # 10+
        return f"Poor ({avg_vr:.1f}%, high energy waste)"


def _calculate_vo_trend(
    activity_id: int, avg_vo: float | None, db_conn: Any
) -> str | None:
    """
    Analyze vertical oscillation trend over splits.

    Analyzes:
    - Coefficient of variation (CV) for consistency
    - First half vs second half trend
    - Fatigue indicators

    Args:
        activity_id: Activity ID
        avg_vo: Average VO (for validation)
        db_conn: DuckDB connection

    Returns:
        VO trend string or None

    Examples:
        >>> # Mock example
        >>> _calculate_vo_trend(12345, 8.5, mock_conn)
        'Stable (8.5cm avg, CV=6%, consistent)'
    """
    if avg_vo is None:
        return None

    # Get all split VOs from splits table
    vos = db_conn.execute(
        """
        SELECT vertical_oscillation
        FROM splits
        WHERE activity_id = ? AND vertical_oscillation IS NOT NULL
        ORDER BY split_index
        """,
        [activity_id],
    ).fetchall()

    if len(vos) < 3:
        return f"Insufficient data ({len(vos)} splits)"

    # Extract VO values
    vo_values = [v[0] for v in vos]

    # Calculate statistics
    avg = sum(vo_values) / len(vo_values)
    std = (sum((v - avg) ** 2 for v in vo_values) / len(vo_values)) ** 0.5
    cv = (std / avg) * 100  # Coefficient of variation

    # Check trend (first half vs second half)
    mid = len(vo_values) // 2
    first_half_avg = sum(vo_values[:mid]) / mid
    second_half_avg = sum(vo_values[mid:]) / (len(vo_values) - mid)
    change_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100

    # Consistency rating
    if cv < 5:
        consistency = "Very stable"
    elif cv < 10:
        consistency = "Stable"
    else:
        consistency = "Variable"

    # Trend description
    if abs(change_pct) < 3:
        trend = "consistent"
    elif change_pct > 0:
        trend = f"increasing (+{change_pct:.1f}%, fatigue indicator)"
    else:
        trend = f"decreasing ({change_pct:.1f}%)"

    return f"{consistency} ({avg:.1f}cm avg, CV={cv:.0f}%, {trend})"


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
    conn: Any | None = None,
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
        conn: Optional DuckDB connection (for connection reuse, Phase 5 optimization)

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

        # Phase 5 optimization: Reuse connection if provided
        if conn is not None:
            # Use provided connection (no close needed)
            _insert_form_efficiency_with_connection(conn, activity_id, form_eff_summary)
        else:
            # Open new connection (backward compatible)
            connection = duckdb.connect(str(db_path))
            try:
                _insert_form_efficiency_with_connection(
                    connection, activity_id, form_eff_summary
                )
            finally:
                connection.close()

        logger.info(
            f"Successfully inserted form efficiency data for activity {activity_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting form efficiency: {e}")
        return False


def _insert_form_efficiency_with_connection(
    conn: Any, activity_id: int, form_eff_summary: dict
) -> None:
    """Helper function to insert form efficiency with a given connection."""
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
