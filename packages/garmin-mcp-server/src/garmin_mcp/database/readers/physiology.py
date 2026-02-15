"""
Physiology reader for DuckDB.

Handles queries to hr_efficiency, heart_rate_zones, vo2_max,
and lactate_threshold tables.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class PhysiologyReader(BaseDBReader):
    """Reader for physiological metrics (HR, VO2 max, lactate threshold)."""

    def get_hr_efficiency_analysis(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get HR efficiency analysis from hr_efficiency table.

        Args:
            activity_id: Activity ID

        Returns:
            HR efficiency data with zone distribution and training type.
            None if activity not found.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        primary_zone,
                        zone_distribution_rating,
                        hr_stability,
                        aerobic_efficiency,
                        training_quality,
                        zone2_focus,
                        zone4_threshold_work,
                        training_type,
                        zone1_percentage,
                        zone2_percentage,
                        zone3_percentage,
                        zone4_percentage,
                        zone5_percentage
                    FROM hr_efficiency
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                return {
                    "primary_zone": result[0],
                    "zone_distribution_rating": result[1],
                    "hr_stability": result[2],
                    "aerobic_efficiency": result[3],
                    "training_quality": result[4],
                    "zone2_focus": bool(result[5]),
                    "zone4_threshold_work": bool(result[6]),
                    "training_type": result[7],
                    "zone_percentages": {
                        "zone1": result[8],
                        "zone2": result[9],
                        "zone3": result[10],
                        "zone4": result[11],
                        "zone5": result[12],
                    },
                }

        except Exception as e:
            logger.error(f"Error getting HR efficiency analysis: {e}")
            return None

    def get_heart_rate_zones_detail(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get heart rate zones detail from heart_rate_zones table.

        Args:
            activity_id: Activity ID

        Returns:
            Heart rate zones data with boundaries and time distribution.
            None if activity not found.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        zone_number,
                        zone_low_boundary,
                        zone_high_boundary,
                        time_in_zone_seconds,
                        zone_percentage
                    FROM heart_rate_zones
                    WHERE activity_id = ?
                    ORDER BY zone_number
                    """,
                    [activity_id],
                ).fetchall()

                if not result:
                    return None

                zones = []
                for row in result:
                    zones.append(
                        {
                            "zone_number": row[0],
                            "low_boundary": row[1],
                            "high_boundary": row[2],
                            "time_in_zone_seconds": row[3],
                            "zone_percentage": row[4],
                        }
                    )

                return {"zones": zones}

        except Exception as e:
            logger.error(f"Error getting heart rate zones detail: {e}")
            return None

    @staticmethod
    def _get_vo2_max_category(vo2_max_value: float | None) -> str:
        """
        Convert VO2 max value to Japanese category label.

        Based on ACSM guidelines for adult males.

        Args:
            vo2_max_value: VO2 max value in ml/kg/min

        Returns:
            Japanese category label
        """
        if vo2_max_value is None:
            return "不明"

        if vo2_max_value >= 47:
            return "優秀"
        elif vo2_max_value >= 42:
            return "良好"
        elif vo2_max_value >= 38:
            return "平均"
        elif vo2_max_value >= 34:
            return "やや低い"
        else:
            return "低い"

    def get_vo2_max_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get VO2 max data from vo2_max table.

        Falls back to most recent VO2 max data before activity date
        if not found for specific activity.

        Args:
            activity_id: Activity ID

        Returns:
            VO2 max data with precise value and category.
            None if no data found.
        """
        try:
            with self._get_connection() as conn:
                # First try: Get VO2 max for this specific activity
                result = conn.execute(
                    """
                    SELECT
                        precise_value,
                        value,
                        date,
                        category
                    FROM vo2_max
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if result:
                    return {
                        "precise_value": result[0],
                        "value": result[1],
                        "date": str(result[2]) if result[2] else None,
                        "category": self._get_vo2_max_category(result[0]),
                    }

                # Fallback: Get most recent VO2 max before or on activity date
                activity_date = conn.execute(
                    """
                    SELECT start_time_local::DATE
                    FROM activities
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not activity_date:
                    return None

                result = conn.execute(
                    """
                    SELECT
                        precise_value,
                        value,
                        date,
                        category
                    FROM vo2_max
                    WHERE date <= ?
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    [activity_date[0]],
                ).fetchone()

                if not result:
                    return None

                return {
                    "precise_value": result[0],
                    "value": result[1],
                    "date": str(result[2]) if result[2] else None,
                    "category": self._get_vo2_max_category(result[0]),
                }

        except Exception as e:
            logger.error(f"Error getting VO2 max data: {e}")
            return None

    def get_lactate_threshold_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get lactate threshold data from lactate_threshold table.

        Args:
            activity_id: Activity ID

        Returns:
            Lactate threshold data with HR, speed, and power metrics.
            None if activity not found.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        heart_rate,
                        speed_mps,
                        date_hr,
                        functional_threshold_power,
                        power_to_weight,
                        weight,
                        date_power
                    FROM lactate_threshold
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                return {
                    "heart_rate": result[0],
                    "speed_mps": result[1],
                    "date_hr": str(result[2]) if result[2] else None,
                    "functional_threshold_power": result[3],
                    "power_to_weight": result[4],
                    "weight": result[5],
                    "date_power": str(result[6]) if result[6] else None,
                }

        except Exception as e:
            logger.error(f"Error getting lactate threshold data: {e}")
            return None
