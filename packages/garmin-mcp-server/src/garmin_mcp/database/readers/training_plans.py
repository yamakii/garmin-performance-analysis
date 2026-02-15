"""Training plan DB reader."""

from __future__ import annotations

import json
import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class TrainingPlanReader(BaseDBReader):
    """Reads training plans from DuckDB."""

    def get_training_plan(
        self,
        plan_id: str,
        week_number: int | None = None,
        summary_only: bool = False,
    ) -> dict[str, Any]:
        """Get training plan data.

        Args:
            plan_id: Plan identifier
            week_number: Optional specific week to retrieve
            summary_only: If True, exclude individual workouts

        Returns:
            Dict with plan data and optionally workouts
        """
        with self._get_connection() as conn:
            plan_row = conn.execute(
                "SELECT * FROM training_plans WHERE plan_id = ?",
                [plan_id],
            ).fetchone()

            if plan_row is None:
                return {"error": f"Plan {plan_id} not found"}

            columns = [desc[0] for desc in conn.description]
            plan_data = dict(zip(columns, plan_row, strict=False))

            # Parse pace_zones JSON
            if plan_data.get("pace_zones_json"):
                plan_data["pace_zones"] = json.loads(plan_data.pop("pace_zones_json"))

            if summary_only:
                # Add workout count only
                count_row = conn.execute(
                    "SELECT COUNT(*) FROM planned_workouts WHERE plan_id = ?",
                    [plan_id],
                ).fetchone()
                plan_data["total_workouts"] = count_row[0] if count_row else 0
                return plan_data

            # Get workouts
            query = "SELECT * FROM planned_workouts WHERE plan_id = ?"
            params: list[Any] = [plan_id]
            if week_number is not None:
                query += " AND week_number = ?"
                params.append(week_number)
            query += " ORDER BY week_number, day_of_week"

            workout_rows = conn.execute(query, params).fetchall()
            workout_columns = [desc[0] for desc in conn.description]

            workouts = []
            for row in workout_rows:
                workout = dict(zip(workout_columns, row, strict=False))
                if workout.get("intervals_json"):
                    workout["intervals"] = json.loads(workout.pop("intervals_json"))
                workouts.append(workout)

            plan_data["workouts"] = workouts
            return plan_data
