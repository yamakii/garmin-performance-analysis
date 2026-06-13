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

    def get_form_baseline_trend(
        self,
        activity_id: int,
        activity_date: str,
        user_id: str = "default",
        condition_group: str = "flat_road",
    ) -> dict[str, Any]:
        """Get form baseline trend by comparing current vs 1-month-prior baselines.

        Reads coefficient baselines from form_baseline_history for the period
        containing ``activity_date`` and the period one month earlier, then
        computes per-metric deltas.

        Args:
            activity_id: Activity ID (echoed in the result).
            activity_date: Activity date in YYYY-MM-DD format.
            user_id: Baseline owner (default "default").
            condition_group: Baseline condition group (default "flat_road").

        Returns:
            Dict with keys ``success`` (bool) and either ``error`` (str) or
            ``activity_id``/``activity_date``/``metrics`` (dict). Mirrors the
            previous handler implementation exactly.
        """
        from datetime import datetime

        from dateutil.relativedelta import relativedelta

        try:
            with self._get_connection() as conn:
                # Get current period baseline
                current_baselines = conn.execute(
                    """
                    SELECT metric, coef_d, coef_b, period_start, period_end
                    FROM form_baseline_history
                    WHERE user_id = ?
                      AND condition_group = ?
                      AND period_start <= ?
                      AND period_end >= ?
                    ORDER BY metric
                    """,
                    [user_id, condition_group, activity_date, activity_date],
                ).fetchall()

                if not current_baselines:
                    return {
                        "success": False,
                        "error": f"No baseline found for {activity_date}",
                    }

                # Calculate 1 month before the current period start
                current_period_start = datetime.strptime(
                    str(current_baselines[0][3]), "%Y-%m-%d"
                )
                one_month_before = current_period_start - relativedelta(months=1)
                target_date = one_month_before.strftime("%Y-%m-%d")

                # Get previous period baseline (1 month before)
                previous_baselines = conn.execute(
                    """
                    SELECT metric, coef_d, coef_b, period_start, period_end
                    FROM form_baseline_history
                    WHERE user_id = ?
                      AND condition_group = ?
                      AND period_start <= ?
                      AND period_end >= ?
                    ORDER BY metric
                    """,
                    [user_id, condition_group, target_date, target_date],
                ).fetchall()

            if not previous_baselines:
                return {
                    "success": False,
                    "error": (
                        "No previous baseline found for comparison "
                        f"(target: {target_date})"
                    ),
                }

            # Build result with current and previous coefficients
            metrics_data: dict[str, Any] = {}
            for curr in current_baselines:
                metric = curr[0]
                metrics_data[metric] = {
                    "current": {
                        "coef_d": curr[1],
                        "coef_b": curr[2],
                        "period": f"{curr[3]} to {curr[4]}",
                    }
                }

            for prev in previous_baselines:
                metric = prev[0]
                if metric in metrics_data:
                    metrics_data[metric]["previous"] = {
                        "coef_d": prev[1],
                        "coef_b": prev[2],
                        "period": f"{prev[3]} to {prev[4]}",
                    }
                    # Calculate deltas
                    if (
                        metrics_data[metric]["current"]["coef_d"] is not None
                        and prev[1] is not None
                    ):
                        metrics_data[metric]["delta_d"] = (
                            metrics_data[metric]["current"]["coef_d"] - prev[1]
                        )
                    if (
                        metrics_data[metric]["current"]["coef_b"] is not None
                        and prev[2] is not None
                    ):
                        metrics_data[metric]["delta_b"] = (
                            metrics_data[metric]["current"]["coef_b"] - prev[2]
                        )

            return {
                "success": True,
                "activity_id": activity_id,
                "activity_date": activity_date,
                "metrics": metrics_data,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

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
