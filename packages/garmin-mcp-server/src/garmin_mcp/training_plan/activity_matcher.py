"""Match actual activities to planned workouts using date-based matching."""

import logging
from datetime import date, timedelta

from garmin_mcp.database.connection import get_connection
from garmin_mcp.training_plan.models import WorkoutMatch
from garmin_mcp.utils.paths import get_database_dir

logger = logging.getLogger(__name__)


class ActivityMatcher:
    """Matches actual activities to planned workouts.

    Uses date-based matching only (+-1 day tolerance).
    Distance and type are not checked because the user may have
    changed the planned workout content.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def _get_db_path(self) -> str:
        if self._db_path is not None:
            return self._db_path
        return str(get_database_dir() / "garmin_performance.duckdb")

    def match_activities(self, plan_id: str, version: int) -> list[WorkoutMatch]:
        """Match completed activities to planned workouts.

        Algorithm:
        1. Query planned_workouts (non-rest, with workout_date) for plan+version
        2. Query activities within plan date range (+- 1 day buffer)
        3. For each planned workout (sorted by date):
           - Find unmatched activities within +-1 day
           - If multiple candidates, pick closest date
        4. Return matches

        Note: Distance/type are not validated -- user may change workout content.
        """
        with get_connection(self._get_db_path()) as conn:
            # 1. Get planned workouts (non-rest, with dates)
            workout_rows = conn.execute(
                """
                SELECT workout_id, week_number, workout_date
                FROM planned_workouts
                WHERE plan_id = ? AND version = ?
                  AND workout_type != 'rest'
                  AND workout_date IS NOT NULL
                ORDER BY workout_date
                """,
                [plan_id, version],
            ).fetchall()

            if not workout_rows:
                return []

            # 2. Determine date range for activities
            first_date = self._to_date(workout_rows[0][2])
            last_date = self._to_date(workout_rows[-1][2])
            range_start = first_date - timedelta(days=1)
            range_end = last_date + timedelta(days=1)

            # 3. Get activities in range
            activity_rows = conn.execute(
                """
                SELECT activity_id, activity_date
                FROM activities
                WHERE activity_date >= ? AND activity_date <= ?
                ORDER BY activity_date
                """,
                [str(range_start), str(range_end)],
            ).fetchall()

            if not activity_rows:
                return []

            # 4. Match: for each workout, find closest unmatched activity within +-1 day
            matched_activity_ids: set[int] = set()
            matches: list[WorkoutMatch] = []

            for workout_id, _week_number, workout_date_raw in workout_rows:
                workout_date = self._to_date(workout_date_raw)
                best_match: tuple[int, str, int] | None = None  # (id, date, distance)

                for activity_id, activity_date_raw in activity_rows:
                    if activity_id in matched_activity_ids:
                        continue

                    activity_date = self._to_date(activity_date_raw)
                    day_diff = abs((activity_date - workout_date).days)

                    if day_diff <= 1 and (
                        best_match is None or day_diff < best_match[2]
                    ):
                        best_match = (
                            activity_id,
                            str(activity_date),
                            day_diff,
                        )

                if best_match is not None:
                    matched_activity_ids.add(best_match[0])
                    matches.append(
                        WorkoutMatch(
                            workout_id=workout_id,
                            actual_activity_id=best_match[0],
                            activity_date=best_match[1],
                        )
                    )

            return matches

    def get_completed_weeks(self, plan_id: str, version: int) -> tuple[set[int], int]:
        """Return (completed week numbers, last_completed_week).

        A week is "completed" if it has at least one matched activity.
        Returns (empty set, 0) if no matches.
        """
        matches = self.match_activities(plan_id, version)
        if not matches:
            return set(), 0

        # Get week numbers for matched workouts
        with get_connection(self._get_db_path()) as conn:
            matched_workout_ids = [m.workout_id for m in matches]
            placeholders = ", ".join(["?"] * len(matched_workout_ids))
            rows = conn.execute(
                f"""
                SELECT DISTINCT week_number
                FROM planned_workouts
                WHERE workout_id IN ({placeholders})
                  AND plan_id = ? AND version = ?
                """,
                [*matched_workout_ids, plan_id, version],
            ).fetchall()

            completed_weeks = {row[0] for row in rows}
            last_completed = max(completed_weeks) if completed_weeks else 0
            return completed_weeks, last_completed

    @staticmethod
    def _to_date(val: object) -> date:
        """Convert date-like value to date object."""
        if isinstance(val, date):
            return val
        return date.fromisoformat(str(val))
