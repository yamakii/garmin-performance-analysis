"""
Workout comparison tools for finding and analyzing similar past activities.

This module provides tools to search for similar workouts based on pace and distance,
calculate similarity scores, and generate performance comparison insights.
"""

import logging
from typing import Any

import duckdb

from tools.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class WorkoutComparator:
    """Find and compare similar past workouts.

    Provides similarity search based on:
    - Pace tolerance (default ±10%)
    - Distance tolerance (default ±10%)
    - Optional terrain matching
    - Optional activity type filtering
    - Optional date range filtering
    """

    def __init__(self, db_path: str | None = None):
        """Initialize workout comparator.

        Args:
            db_path: Optional path to DuckDB database
        """
        self.db_reader = GarminDBReader(db_path)

    # Training type hierarchical similarity matrix
    # Based on training intensity and purpose
    # All keys are sorted tuples for symmetric lookup
    TRAINING_TYPE_SIMILARITY = {
        # Recovery - very low intensity
        ("recovery", "recovery"): 1.0,
        ("base", "recovery"): 0.6,
        ("long_run", "recovery"): 0.5,
        ("recovery", "tempo"): 0.3,
        ("recovery", "threshold"): 0.2,
        ("recovery", "vo2_max"): 0.2,
        ("anaerobic", "recovery"): 0.2,
        ("interval", "recovery"): 0.2,
        ("recovery", "sprint"): 0.2,
        # Base - low intensity
        ("base", "base"): 1.0,
        ("base", "long_run"): 0.9,
        ("base", "tempo"): 0.4,
        ("base", "threshold"): 0.3,
        ("base", "vo2_max"): 0.2,
        ("anaerobic", "base"): 0.2,
        ("base", "interval"): 0.2,
        ("base", "sprint"): 0.2,
        # Long Run - low intensity
        ("long_run", "long_run"): 1.0,
        ("long_run", "tempo"): 0.4,
        ("long_run", "threshold"): 0.3,
        ("long_run", "vo2_max"): 0.2,
        ("anaerobic", "long_run"): 0.2,
        ("interval", "long_run"): 0.2,
        ("long_run", "sprint"): 0.2,
        # Tempo - mid intensity
        ("tempo", "tempo"): 1.0,
        ("tempo", "threshold"): 0.8,
        ("tempo", "vo2_max"): 0.3,
        ("anaerobic", "tempo"): 0.3,
        ("interval", "tempo"): 0.3,
        ("sprint", "tempo"): 0.2,
        # Threshold - mid-high intensity
        ("threshold", "threshold"): 1.0,
        ("threshold", "vo2_max"): 0.4,
        ("anaerobic", "threshold"): 0.3,
        ("interval", "threshold"): 0.3,
        ("sprint", "threshold"): 0.2,
        # VO2 Max - high intensity
        ("vo2_max", "vo2_max"): 1.0,
        ("anaerobic", "vo2_max"): 0.7,
        ("interval", "vo2_max"): 0.6,
        ("sprint", "vo2_max"): 0.3,
        # Anaerobic - high intensity
        ("anaerobic", "anaerobic"): 1.0,
        ("anaerobic", "interval"): 0.8,
        ("anaerobic", "sprint"): 0.4,
        # Interval - very high intensity
        ("interval", "interval"): 1.0,
        ("interval", "sprint"): 0.7,
        # Sprint - maximum intensity
        ("sprint", "sprint"): 1.0,
        # Unknown - default similarity
        ("unknown", "unknown"): 1.0,
    }

    def _get_training_type_similarity(self, type1: str, type2: str) -> float:
        """Get training type similarity score from matrix.

        Returns similarity based on hierarchical training type relationships:
        - Same type: 1.0
        - Same category (e.g., Tempo-Threshold): 0.7-0.9
        - Adjacent category (e.g., Base-Tempo): 0.4-0.6
        - Different category (e.g., Recovery-Sprint): 0.2-0.3

        Args:
            type1: First training type (e.g., "tempo")
            type2: Second training type (e.g., "threshold")

        Returns:
            Similarity score (0.0-1.0)
        """
        # Normalize to lowercase
        type1 = type1.lower()
        type2 = type2.lower()

        # Create sorted key for symmetric lookup
        sorted_types = sorted([type1, type2])
        key = (sorted_types[0], sorted_types[1])

        # Return similarity from matrix, default to 0.3 for unknown combinations
        return self.TRAINING_TYPE_SIMILARITY.get(key, 0.3)

    def _get_activity_temperature(self, activity_id: int) -> float | None:
        """Get temperature for activity from database.

        Args:
            activity_id: Activity ID

        Returns:
            Temperature in Celsius, or None if not available
        """
        try:
            weather_data = self.db_reader.get_weather_data(activity_id)
            if not weather_data:
                return None

            return weather_data.get("temperature_c")

        except Exception as e:
            logger.error(f"Error getting temperature for activity {activity_id}: {e}")
            return None

    def _execute_query(self, query: str, params: list[Any]):
        """Execute a database query.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Query result object
        """
        conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)
        result = conn.execute(query, params)
        return result

    def find_similar_workouts(
        self,
        activity_id: int,
        pace_tolerance: float = 0.1,
        distance_tolerance: float = 0.1,
        terrain_match: bool = False,
        activity_type_filter: str | None = None,
        date_range: tuple[str, str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Find similar past workouts based on pace and distance.

        Args:
            activity_id: Target activity ID to find similar workouts for
            pace_tolerance: Pace tolerance as fraction (0.1 = ±10%)
            distance_tolerance: Distance tolerance as fraction (0.1 = ±10%)
            terrain_match: Whether to match terrain characteristics
            activity_type_filter: Optional activity type keyword filter
            date_range: Optional (start_date, end_date) tuple in YYYY-MM-DD format
            limit: Maximum number of results to return

        Returns:
            Dict with similar workouts:
            {
                "target_activity": {
                    "activity_id": int,
                    "activity_date": str,
                    "activity_name": str,
                    "avg_pace": float,
                    "avg_heart_rate": float,
                    "distance_km": float,
                    ...
                },
                "similar_activities": [
                    {
                        "activity_id": int,
                        "activity_date": str,
                        "similarity_score": float,
                        "pace_diff": float,
                        "hr_diff": float,
                        "interpretation": str
                    }
                ],
                "comparison_summary": str
            }
        """
        # Get target activity data
        target = self._get_target_activity(activity_id)
        if not target:
            return {
                "target_activity": None,
                "similar_activities": [],
                "comparison_summary": f"Activity {activity_id} not found",
            }

        # Calculate pace and distance ranges
        pace_min = target["avg_pace"] * (1 - pace_tolerance)
        pace_max = target["avg_pace"] * (1 + pace_tolerance)
        distance_min = target["distance_km"] * (1 - distance_tolerance)
        distance_max = target["distance_km"] * (1 + distance_tolerance)

        # Build SQL query
        query = """
            SELECT
                a.activity_id,
                a.date,
                a.activity_name,
                a.avg_pace_seconds_per_km,
                a.avg_heart_rate,
                a.total_distance_km,
                a.aerobic_te,
                a.anaerobic_te,
                a.avg_cadence,
                a.avg_power
            FROM activities a
            WHERE a.activity_id != ?
              AND a.avg_pace_seconds_per_km BETWEEN ? AND ?
              AND a.total_distance_km BETWEEN ? AND ?
        """

        params = [activity_id, pace_min, pace_max, distance_min, distance_max]

        # Add activity type filter
        if activity_type_filter:
            query += " AND a.activity_name LIKE ?"
            params.append(f"%{activity_type_filter}%")

        # Add date range filter
        if date_range:
            query += " AND a.date BETWEEN ? AND ?"
            params.extend(date_range)

        # Order by pace similarity and limit results
        query += " ORDER BY ABS(a.avg_pace_seconds_per_km - ?) ASC LIMIT ?"
        params.extend([target["avg_pace"], limit])

        # Execute query
        try:
            results = self._execute_query(query, params).fetchall()

            # Convert to dict format
            similar_activities = []
            for row in results:
                candidate = {
                    "activity_id": row[0],
                    "activity_date": row[1],
                    "activity_name": row[2],
                    "avg_pace": row[3],
                    "avg_heart_rate": row[4],
                    "distance_km": row[5],
                    "aerobic_te": row[6],
                    "anaerobic_te": row[7],
                    "avg_cadence": row[8],
                    "avg_power": row[9],
                }

                # Calculate similarity metrics
                similarity_score = self._calculate_similarity_score(target, candidate)
                pace_diff = candidate["avg_pace"] - target["avg_pace"]
                hr_diff = (
                    candidate["avg_heart_rate"] - target["avg_heart_rate"]
                    if candidate["avg_heart_rate"] and target["avg_heart_rate"]
                    else 0.0
                )

                similar_activities.append(
                    {
                        "activity_id": candidate["activity_id"],
                        "activity_date": candidate["activity_date"],
                        "activity_name": candidate["activity_name"],
                        "similarity_score": round(similarity_score, 1),
                        "pace_diff": round(pace_diff, 1),
                        "hr_diff": round(hr_diff, 1),
                        "interpretation": self._generate_interpretation(
                            pace_diff, hr_diff
                        ),
                    }
                )

            # Generate comparison summary
            if similar_activities:
                avg_similarity = sum(
                    a["similarity_score"] for a in similar_activities
                ) / len(similar_activities)
                summary = f"{len(similar_activities)}件の類似ワークアウトを発見。平均類似度: {avg_similarity:.1f}%"
            else:
                summary = "類似するワークアウトが見つかりませんでした"

            return {
                "target_activity": target,
                "similar_activities": similar_activities,
                "comparison_summary": summary,
            }

        except Exception as e:
            logger.error(f"Error finding similar workouts: {e}")
            return {
                "target_activity": target,
                "similar_activities": [],
                "comparison_summary": f"Error: {str(e)}",
            }

    def _get_target_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Get target activity data from database.

        Args:
            activity_id: Activity ID

        Returns:
            Activity data dict or None if not found
        """
        try:
            query = """
                SELECT
                    activity_id,
                    date,
                    activity_name,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    total_distance_km,
                    aerobic_te,
                    anaerobic_te,
                    avg_cadence,
                    avg_power
                FROM activities
                WHERE activity_id = ?
            """
            row = self._execute_query(query, [activity_id]).fetchone()

            if not row:
                return None

            return {
                "activity_id": row[0],
                "activity_date": row[1],
                "activity_name": row[2],
                "avg_pace": row[3],
                "avg_heart_rate": row[4],
                "distance_km": row[5],
                "aerobic_te": row[6],
                "anaerobic_te": row[7],
                "avg_cadence": row[8],
                "avg_power": row[9],
            }

        except Exception as e:
            logger.error(f"Error getting target activity {activity_id}: {e}")
            return None

    def _calculate_similarity_score(
        self, target: dict[str, Any], candidate: dict[str, Any]
    ) -> float:
        """Calculate similarity score between target and candidate workouts.

        Similarity is based on:
        - Pace similarity (45% weight)
        - Distance similarity (35% weight)
        - Training type similarity (20% weight)

        Args:
            target: Target activity data
            candidate: Candidate activity data

        Returns:
            Similarity score (0-100%)
        """
        # Pace similarity (1.0 = identical, 0.0 = completely different)
        pace_similarity = (
            1 - abs(candidate["avg_pace"] - target["avg_pace"]) / target["avg_pace"]
        )

        # Distance similarity
        distance_similarity = (
            1
            - abs(candidate["distance_km"] - target["distance_km"])
            / target["distance_km"]
        )

        # Training type similarity
        target_type = target.get("training_type", "unknown")
        candidate_type = candidate.get("training_type", "unknown")
        type_similarity = self._get_training_type_similarity(
            target_type, candidate_type
        )

        # Weighted average (pace 45%, distance 35%, training type 20%)
        similarity = (
            pace_similarity * 0.45 + distance_similarity * 0.35 + type_similarity * 0.20
        ) * 100

        return float(
            max(0.0, min(100.0, similarity))
        )  # Clamp to 0-100%  # Clamp to 0-100%  # Clamp to 0-100%

    def _generate_interpretation(
        self, pace_diff: float, hr_diff: float, temp_diff: float | None = None
    ) -> str:
        """Generate human-readable interpretation of performance difference.

        Args:
            pace_diff: Pace difference in seconds/km (negative = faster)
            hr_diff: Heart rate difference in bpm (negative = lower)
            temp_diff: Temperature difference in Celsius (None if unavailable)

        Returns:
            Japanese interpretation string with temperature context when applicable

        Examples:
            - "ペース: 3.2秒/km速い, 心拍: 12bpm高い（気温+6°C影響）"
            - "ペース: 2.1秒/km遅い, 心拍: 5bpm低い（気温-2°C影響）"
            - "ペース: 1.0秒/km速い, 心拍: 3bpm高い"  # No temp data
        """
        pace_text = f"{abs(pace_diff):.1f}秒/km{'速い' if pace_diff < 0 else '遅い'}"

        hr_text = f"{abs(hr_diff):.0f}bpm{'低い' if hr_diff < 0 else '高い'}"

        # Add temperature context if difference is significant (>1°C)
        if temp_diff is not None and abs(temp_diff) > 1.0:
            temp_context = (
                f"（気温{'+' if temp_diff > 0 else ''}{temp_diff:.0f}°C影響）"
            )
            hr_text += temp_context

        return f"ペース: {pace_text}, 心拍: {hr_text}"
