"""Garmin Connect workout uploader."""

from __future__ import annotations

import logging
from typing import Any

from garmin_mcp.database.readers.training_plans import TrainingPlanReader
from garmin_mcp.training_plan.models import PaceZones, PlannedWorkout, WorkoutType
from garmin_mcp.training_plan.workout_builder import GarminWorkoutBuilder

logger = logging.getLogger(__name__)


class GarminWorkoutUploader:
    """Uploads workouts to Garmin Connect."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._reader = TrainingPlanReader(db_path=db_path)

    def _get_garmin_client(self) -> Any:
        """Get authenticated Garmin Connect client."""
        from garmin_mcp.ingest.garmin_worker import GarminIngestWorker

        worker = GarminIngestWorker()
        return worker.get_garmin_client()

    def upload_workout(self, workout_id: str) -> dict[str, Any]:
        """Upload a single workout to Garmin Connect.

        Args:
            workout_id: Workout ID from planned_workouts table

        Returns:
            Dict with upload status and Garmin workout ID
        """
        with self._reader._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM planned_workouts WHERE workout_id = ?",
                [workout_id],
            ).fetchone()

            if row is None:
                return {"error": f"Workout {workout_id} not found"}

            columns = [desc[0] for desc in conn.description]
            workout_data = dict(zip(columns, row, strict=False))

            # Get plan's pace zones
            plan_row = conn.execute(
                "SELECT pace_zones_json FROM training_plans WHERE plan_id = ?",
                [workout_data["plan_id"]],
            ).fetchone()

            if not plan_row:
                return {"error": f"Plan {workout_data['plan_id']} not found"}

            pace_zones = PaceZones.model_validate_json(plan_row[0])

        # Build PlannedWorkout from DB data
        from garmin_mcp.training_plan.models import IntervalDetail, PeriodizationPhase

        intervals = None
        if workout_data.get("intervals_json"):
            intervals = IntervalDetail.model_validate_json(
                workout_data["intervals_json"]
            )

        planned = PlannedWorkout(
            workout_id=workout_data["workout_id"],
            plan_id=workout_data["plan_id"],
            week_number=workout_data["week_number"],
            day_of_week=workout_data["day_of_week"],
            workout_type=WorkoutType(workout_data["workout_type"]),
            description_ja=workout_data.get("description_ja"),
            target_distance_km=workout_data.get("target_distance_km"),
            target_duration_minutes=workout_data.get("target_duration_minutes"),
            target_pace_low=workout_data.get("target_pace_low"),
            target_pace_high=workout_data.get("target_pace_high"),
            intervals=intervals,
            phase=PeriodizationPhase(workout_data["phase"]),
        )

        # Build Garmin workout
        garmin_workout = GarminWorkoutBuilder.build(planned, pace_zones)

        # Upload
        try:
            client = self._get_garmin_client()
            result = client.upload_workout(garmin_workout)
            garmin_id = result.get("workoutId") if isinstance(result, dict) else None

            # Update DB with Garmin workout ID
            if garmin_id:
                import duckdb

                db_path = self._db_path or str(self._reader.db_path)
                update_conn = duckdb.connect(db_path)
                update_conn.execute(
                    "UPDATE planned_workouts SET garmin_workout_id = ?, uploaded_at = CURRENT_TIMESTAMP WHERE workout_id = ?",
                    [garmin_id, workout_id],
                )
                update_conn.close()

            return {
                "success": True,
                "workout_id": workout_id,
                "garmin_workout_id": garmin_id,
                "workout_name": garmin_workout["workoutName"],
            }
        except Exception as e:
            logger.error(f"Upload failed for {workout_id}: {e}")
            return {"error": str(e), "workout_id": workout_id}

    def upload_plan_workouts(
        self, plan_id: str, week_number: int | None = None
    ) -> dict[str, Any]:
        """Upload all workouts for a plan (or specific week).

        Returns:
            Dict with results for each workout
        """
        plan_data = self._reader.get_training_plan(plan_id, week_number=week_number)

        if "error" in plan_data:
            return plan_data

        workouts = plan_data.get("workouts", [])
        results = []

        for w in workouts:
            if w.get("garmin_workout_id"):
                results.append(
                    {
                        "workout_id": w["workout_id"],
                        "skipped": True,
                        "reason": "Already uploaded",
                    }
                )
                continue

            result = self.upload_workout(w["workout_id"])
            results.append(result)

        return {
            "plan_id": plan_id,
            "week_number": week_number,
            "total": len(workouts),
            "uploaded": sum(1 for r in results if r.get("success")),
            "skipped": sum(1 for r in results if r.get("skipped")),
            "failed": sum(1 for r in results if r.get("error")),
            "results": results,
        }
