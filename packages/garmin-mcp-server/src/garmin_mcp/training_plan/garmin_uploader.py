"""Garmin Connect workout uploader."""

from __future__ import annotations

import hashlib
import json
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

    @staticmethod
    def _workout_fingerprint(garmin_workout: dict[str, Any]) -> str:
        """Create a fingerprint hash from a Garmin workout dict.

        Hashes the workout structure (segments/steps/targets) to detect
        duplicates. workoutName is included since it identifies the workout type.
        """
        canonical = json.dumps(garmin_workout, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def upload_workout(self, workout_id: str, schedule: bool = True) -> dict[str, Any]:
        """Upload a single workout to Garmin Connect.

        Args:
            workout_id: Workout ID from planned_workouts table
            schedule: If True and workout_date is set, schedule on Garmin calendar

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
            workout_date=workout_data.get("workout_date"),
            description_ja=workout_data.get("description_ja"),
            target_distance_km=workout_data.get("target_distance_km"),
            target_duration_minutes=workout_data.get("target_duration_minutes"),
            target_pace_low=workout_data.get("target_pace_low"),
            target_pace_high=workout_data.get("target_pace_high"),
            target_hr_low=workout_data.get("target_hr_low"),
            target_hr_high=workout_data.get("target_hr_high"),
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

            # Schedule on calendar if requested
            scheduled = False
            if schedule and garmin_id and planned.workout_date:
                scheduled = self._schedule_workout(
                    client, garmin_id, str(planned.workout_date)
                )

            return {
                "success": True,
                "workout_id": workout_id,
                "garmin_workout_id": garmin_id,
                "workout_name": garmin_workout["workoutName"],
                "scheduled": scheduled,
                "scheduled_date": str(planned.workout_date) if scheduled else None,
            }
        except Exception as e:
            logger.error(f"Upload failed for {workout_id}: {e}")
            return {"error": str(e), "workout_id": workout_id}

    def _schedule_workout(
        self, client: Any, garmin_workout_id: int, scheduled_date: str
    ) -> bool:
        """Schedule a workout on Garmin Connect calendar.

        Args:
            client: Authenticated Garmin Connect client
            garmin_workout_id: Garmin workout ID (from upload)
            scheduled_date: Date in YYYY-MM-DD format

        Returns:
            True if scheduling succeeded
        """
        try:
            url = f"/workout-service/schedule/{garmin_workout_id}"
            payload = {"date": scheduled_date}
            client.garth.post("connectapi", url, json=payload, api=True)
            logger.info(f"Scheduled workout {garmin_workout_id} on {scheduled_date}")
            return True
        except Exception as e:
            logger.warning(
                f"Failed to schedule workout {garmin_workout_id} on {scheduled_date}: {e}"
            )
            return False

    def _reuse_workout(
        self,
        workout_id: str,
        garmin_workout_id: int,
        workout_date: str | None,
        schedule: bool,
    ) -> dict[str, Any]:
        """Reuse an existing Garmin workout for a different scheduled date.

        Sets the garmin_workout_id on the DB row and optionally schedules it.
        """
        import duckdb

        db_path = self._db_path or str(self._reader.db_path)
        update_conn = duckdb.connect(db_path)
        update_conn.execute(
            "UPDATE planned_workouts SET garmin_workout_id = ?, uploaded_at = CURRENT_TIMESTAMP WHERE workout_id = ?",
            [garmin_workout_id, workout_id],
        )
        update_conn.close()

        scheduled = False
        if schedule and workout_date:
            try:
                client = self._get_garmin_client()
                scheduled = self._schedule_workout(
                    client, garmin_workout_id, str(workout_date)
                )
            except Exception as e:
                logger.warning(f"Failed to schedule reused workout: {e}")

        return {
            "success": True,
            "workout_id": workout_id,
            "garmin_workout_id": garmin_workout_id,
            "reused": True,
            "scheduled": scheduled,
            "scheduled_date": workout_date if scheduled else None,
        }

    def upload_plan_workouts(
        self,
        plan_id: str,
        week_number: int | None = None,
        schedule: bool = True,
    ) -> dict[str, Any]:
        """Upload all workouts for a plan (or specific week).

        Uses fingerprint-based deduplication: identical workout structures
        are uploaded once and reused across multiple scheduled dates.

        Args:
            plan_id: Plan ID
            week_number: Optional specific week to upload
            schedule: If True, schedule workouts on Garmin calendar

        Returns:
            Dict with results for each workout
        """
        plan_data = self._reader.get_training_plan(plan_id, week_number=week_number)

        if "error" in plan_data:
            return plan_data

        workouts = plan_data.get("workouts", [])
        results = []

        # fingerprint → garmin_workout_id mapping for deduplication
        fingerprint_cache: dict[str, int] = {}

        # Get pace zones for fingerprinting
        with self._reader._get_connection() as conn:
            plan_row = conn.execute(
                "SELECT pace_zones_json FROM training_plans WHERE plan_id = ?",
                [plan_id],
            ).fetchone()

        pace_zones = PaceZones.model_validate_json(plan_row[0]) if plan_row else None

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

            # Try to compute fingerprint for deduplication
            fingerprint = None
            if pace_zones:
                try:
                    from garmin_mcp.training_plan.models import (
                        IntervalDetail,
                        PeriodizationPhase,
                    )

                    intervals = None
                    if w.get("intervals"):
                        intervals = IntervalDetail.model_validate(w["intervals"])

                    planned = PlannedWorkout(
                        workout_id=w["workout_id"],
                        plan_id=w["plan_id"],
                        week_number=w["week_number"],
                        day_of_week=w["day_of_week"],
                        workout_type=WorkoutType(w["workout_type"]),
                        description_ja=w.get("description_ja"),
                        target_distance_km=w.get("target_distance_km"),
                        target_duration_minutes=w.get("target_duration_minutes"),
                        target_pace_low=w.get("target_pace_low"),
                        target_pace_high=w.get("target_pace_high"),
                        target_hr_low=w.get("target_hr_low"),
                        target_hr_high=w.get("target_hr_high"),
                        intervals=intervals,
                        phase=PeriodizationPhase(w["phase"]),
                    )
                    garmin_workout = GarminWorkoutBuilder.build(planned, pace_zones)
                    fingerprint = self._workout_fingerprint(garmin_workout)
                except Exception as e:
                    logger.warning(
                        "Fingerprint computation failed for workout %s: %s",
                        w["workout_id"],
                        e,
                        exc_info=True,
                    )
                    fingerprint = None

            # Check if we already uploaded an identical workout
            if fingerprint and fingerprint in fingerprint_cache:
                existing_garmin_id = fingerprint_cache[fingerprint]
                logger.info(
                    f"Reusing workout {existing_garmin_id} for {w['workout_id']} "
                    f"(fingerprint: {fingerprint})"
                )
                result = self._reuse_workout(
                    w["workout_id"],
                    existing_garmin_id,
                    w.get("workout_date"),
                    schedule,
                )
                results.append(result)
                continue

            # Upload new workout
            result = self.upload_workout(w["workout_id"], schedule=schedule)
            results.append(result)

            # Cache fingerprint if upload succeeded
            if (
                fingerprint
                and result.get("success")
                and result.get("garmin_workout_id")
            ):
                fingerprint_cache[fingerprint] = result["garmin_workout_id"]

        reused = sum(1 for r in results if r.get("reused"))
        return {
            "plan_id": plan_id,
            "week_number": week_number,
            "total": len(workouts),
            "uploaded": sum(
                1 for r in results if r.get("success") and not r.get("reused")
            ),
            "reused": reused,
            "skipped": sum(1 for r in results if r.get("skipped")),
            "failed": sum(1 for r in results if r.get("error")),
            "results": results,
        }

    def delete_workout(self, workout_id: str) -> dict[str, Any]:
        """Delete a single workout from Garmin Connect.

        If other planned_workouts share the same garmin_workout_id,
        only clears the DB reference (does not delete from Garmin).
        Only deletes from Garmin when this is the last reference.

        Args:
            workout_id: Workout ID from planned_workouts table

        Returns:
            Dict with deletion status
        """
        with self._reader._get_connection() as conn:
            row = conn.execute(
                "SELECT workout_id, garmin_workout_id FROM planned_workouts WHERE workout_id = ?",
                [workout_id],
            ).fetchone()

            if row is None:
                return {"error": f"Workout {workout_id} not found"}

            garmin_workout_id = row[1]

            if garmin_workout_id is None:
                return {
                    "workout_id": workout_id,
                    "skipped": True,
                    "reason": "Not uploaded to Garmin",
                }

            # Check if other workouts share this garmin_workout_id
            shared_count_row = conn.execute(
                "SELECT COUNT(*) FROM planned_workouts WHERE garmin_workout_id = ? AND workout_id != ?",
                [garmin_workout_id, workout_id],
            ).fetchone()
            shared_count = shared_count_row[0] if shared_count_row else 0

        import duckdb

        db_path = self._db_path or str(self._reader.db_path)

        if shared_count > 0:
            # Other workouts still reference this Garmin workout - just clear DB ref
            update_conn = duckdb.connect(db_path)
            update_conn.execute(
                "UPDATE planned_workouts SET garmin_workout_id = NULL, uploaded_at = NULL WHERE workout_id = ?",
                [workout_id],
            )
            update_conn.close()

            logger.info(
                f"Cleared garmin_workout_id for {workout_id} "
                f"({shared_count} other workouts still reference {garmin_workout_id})"
            )
            return {
                "success": True,
                "workout_id": workout_id,
                "garmin_workout_id": garmin_workout_id,
                "deleted": False,
                "unlinked": True,
                "reason": f"Garmin workout kept ({shared_count} other references)",
            }

        # Last reference - delete from Garmin
        try:
            client = self._get_garmin_client()
            client.connectapi(
                f"/workout-service/workout/{garmin_workout_id}", method="DELETE"
            )

            update_conn = duckdb.connect(db_path)
            update_conn.execute(
                "UPDATE planned_workouts SET garmin_workout_id = NULL, uploaded_at = NULL WHERE workout_id = ?",
                [workout_id],
            )
            update_conn.close()

            return {
                "success": True,
                "workout_id": workout_id,
                "garmin_workout_id": garmin_workout_id,
                "deleted": True,
            }
        except Exception as e:
            logger.error(f"Delete failed for {workout_id}: {e}")
            return {"error": str(e), "workout_id": workout_id}

    def delete_plan_workouts(
        self,
        plan_id: str,
        week_number: int | None = None,
    ) -> dict[str, Any]:
        """Delete all uploaded workouts for a plan (or specific week) from Garmin Connect.

        Args:
            plan_id: Plan ID
            week_number: Optional specific week to delete

        Returns:
            Dict with results for each workout
        """
        plan_data = self._reader.get_training_plan(plan_id, week_number=week_number)

        if "error" in plan_data:
            return plan_data

        workouts = plan_data.get("workouts", [])
        results = []

        for w in workouts:
            if not w.get("garmin_workout_id"):
                results.append(
                    {
                        "workout_id": w["workout_id"],
                        "skipped": True,
                        "reason": "Not uploaded to Garmin",
                    }
                )
                continue

            result = self.delete_workout(w["workout_id"])
            results.append(result)

        return {
            "plan_id": plan_id,
            "week_number": week_number,
            "total": len(workouts),
            "deleted": sum(1 for r in results if r.get("success")),
            "skipped": sum(1 for r in results if r.get("skipped")),
            "failed": sum(1 for r in results if r.get("error")),
            "results": results,
        }
