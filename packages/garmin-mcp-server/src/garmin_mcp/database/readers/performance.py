"""
Performance reader for DuckDB.

Handles queries to performance_trends, activities (weather),
and section_analyses tables.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class PerformanceReader(BaseDBReader):
    """Reader for performance trends, weather, and section analysis data."""

    def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get performance trends data from performance_trends table.

        The ``cadence_consistency`` / ``fatigue_pattern`` columns are not
        returned: they only ever held fixed placeholder text and are now NULL.

        Args:
            activity_id: Activity ID

        Returns:
            Performance trends data with phase breakdowns.
            None if activity not found.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        run_avg_pace_seconds_per_km,
                        run_avg_hr,
                        recovery_splits,
                        recovery_avg_pace_seconds_per_km,
                        recovery_avg_hr,
                        cooldown_avg_pace_seconds_per_km,
                        cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                trends_data = {
                    "pace_consistency": result[0],
                    "hr_drift_percentage": result[1],
                    "warmup_phase": {
                        "avg_pace": result[2],
                        "avg_hr": result[3],
                    },
                    "run_phase": {
                        "avg_pace": result[4],
                        "avg_hr": result[5],
                    },
                    "cooldown_phase": {
                        "avg_pace": result[9],
                        "avg_hr": result[10],
                    },
                }

                # Add recovery_phase only if it exists (4-phase interval training)
                if result[6] is not None:
                    trends_data["recovery_phase"] = {
                        "avg_pace": result[7],
                        "avg_hr": result[8],
                    }

                return trends_data

        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            return None

    def get_weather_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Get weather data from activities table.

        Args:
            activity_id: Activity ID

        Returns:
            Weather data from activity.
            None if activity not found or weather data unavailable.
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    """
                    SELECT
                        temp_celsius,
                        relative_humidity_percent,
                        wind_speed_kmh,
                        wind_direction
                    FROM activities
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()

                if not result:
                    return None

                # Convert wind speed from km/h to m/s
                wind_speed_ms = result[2] / 3.6 if result[2] else None

                # temp_celsius is already stored in Celsius, no conversion needed
                temp_c = result[0]
                # Convert Celsius to Fahrenheit
                temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None

                return {
                    "temperature_c": temp_c,
                    "temperature_f": temp_f,
                    "humidity": result[1],
                    "wind_speed_ms": wind_speed_ms,
                    "wind_direction": result[3],
                }

        except Exception as e:
            logger.error(f"Error getting weather data: {e}")
            return None

    def find_unanalyzed_activities(
        self, start_date: str, end_date: str, required_sections: int = 5
    ) -> list[dict[str, Any]]:
        """Find running activities missing a complete set of section analyses.

        ``activities`` LEFT JOIN ``section_analyses`` aggregated by
        ``activity_id`` within ``[start_date, end_date]``. An activity counts as
        analysed when it has **a ``run_note`` row** (the single coach review that
        replaces the five legacy sections, Epic #1247) **or** at least
        ``required_sections`` distinct legacy section types. All ingested
        activities are runs (non-running types are filtered at ingest), so no
        activity_type filter is needed. DISTINCT is used because append-only
        storage (#720) keeps multiple versions of the same section.

        Args:
            start_date: Inclusive lower bound (YYYY-MM-DD).
            end_date: Inclusive upper bound (YYYY-MM-DD).
            required_sections: Legacy section count considered complete
                (default 5). ``run_note`` rows never count toward it.

        Returns:
            ``[{"activity_id": int, "date": "YYYY-MM-DD", "section_count": int}]``
            where ``section_count`` is the distinct *legacy* section count,
            ordered by date ascending (activity_id as tiebreaker). Empty list on
            error or when every activity is analysed.
        """
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        a.activity_id,
                        a.activity_date,
                        COUNT(DISTINCT s.section_type)
                            FILTER (WHERE s.section_type <> 'run_note')
                            AS section_count
                    FROM activities a
                    LEFT JOIN section_analyses s
                        ON a.activity_id = s.activity_id
                    WHERE a.activity_date BETWEEN ? AND ?
                    GROUP BY a.activity_id, a.activity_date
                    HAVING COUNT(DISTINCT s.section_type)
                               FILTER (WHERE s.section_type <> 'run_note') < ?
                       AND COUNT(*) FILTER (WHERE s.section_type = 'run_note') = 0
                    ORDER BY a.activity_date ASC, a.activity_id ASC
                    """,
                    [start_date, end_date, required_sections],
                ).fetchall()

                return [
                    {
                        "activity_id": row[0],
                        "date": str(row[1]),
                        "section_count": row[2],
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Error finding unanalyzed activities: {e}")
            return []
