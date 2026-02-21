"""Handler for training plan tool calls."""

import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response

logger = logging.getLogger(__name__)

# Safety limits for volume progression (2-tier)
VOLUME_WARNING_THRESHOLD_PCT = 0.15  # 15% warning threshold
VOLUME_HARD_LIMIT_PCT = 0.25  # 25% hard limit

# Workout types prohibited for return_to_run plans
_RETURN_TO_RUN_PROHIBITED_TYPES = {
    "tempo",
    "threshold",
    "interval",
    "repetition",
    "race_pace",
}


class TrainingPlanHandler:
    """Handles training plan-related tool calls."""

    _tool_names: set[str] = {
        "get_current_fitness_summary",
        "save_training_plan",
        "get_training_plan",
        "upload_workout_to_garmin",
        "delete_workout_from_garmin",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_current_fitness_summary":
            return await self._get_current_fitness_summary(arguments)
        elif name == "save_training_plan":
            return await self._save_training_plan(arguments)
        elif name == "get_training_plan":
            return await self._get_training_plan(arguments)
        elif name == "upload_workout_to_garmin":
            return await self._upload_workout_to_garmin(arguments)
        elif name == "delete_workout_from_garmin":
            return await self._delete_workout_from_garmin(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def _get_current_fitness_summary(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor

        lookback_weeks = arguments.get("lookback_weeks", 8)
        try:
            assessor = FitnessAssessor(db_path=str(self._db_reader.db_path))
            summary = assessor.assess(lookback_weeks=lookback_weeks)
            result = summary.model_dump()
        except Exception as e:
            logger.error(f"Fitness assessment failed: {e}")
            result = {"error": str(e)}  # type: ignore[assignment]

        return [TextContent(type="text", text=format_json_response(result))]

    async def _save_training_plan(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.database.inserters.training_plans import insert_training_plan
        from garmin_mcp.training_plan.models import TrainingPlan

        try:
            plan_data = arguments["plan"]

            # Pydantic validation
            plan = TrainingPlan.model_validate(plan_data)

            # Safety checks (2-tier: errors block, warnings pass through)
            errors, warnings = self._validate_plan_safety(plan)
            if errors:
                return [
                    TextContent(
                        type="text",
                        text=format_json_response(
                            {"error": "Safety validation failed", "details": errors}
                        ),
                    )
                ]

            # Save to DuckDB
            insert_training_plan(
                db_path=str(self._db_reader.db_path),
                plan=plan,
            )

            # Build markdown output path
            from garmin_mcp.utils.paths import get_result_dir

            plans_dir = get_result_dir() / "training_plans"
            date_str = str(plan.start_date) if plan.start_date else "unknown"
            md_filename = f"{date_str}_{plan.plan_id}.md"

            result: dict[str, Any] = {
                "status": "saved",
                "plan_id": plan.plan_id,
                "version": plan.version,
                "workout_count": len(plan.workouts),
                "markdown_path": str(plans_dir / md_filename),
            }
            if warnings:
                result["warnings"] = warnings

        except Exception as e:
            logger.error(f"Save training plan failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    @staticmethod
    def _validate_plan_safety(plan: Any) -> tuple[list[str], list[str]]:
        """Run safety checks on a training plan.

        Returns (errors, warnings). Errors block saving; warnings are
        included in the success response but do not prevent saving.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check weekly volume progression (2-tier: warning at 15%, error at 25%)
        volumes = plan.weekly_volumes
        for i in range(1, len(volumes)):
            if volumes[i - 1] > 0:
                increase = (volumes[i] - volumes[i - 1]) / volumes[i - 1]
                if increase > VOLUME_HARD_LIMIT_PCT:
                    errors.append(
                        f"Week {i} to {i + 1}: volume increase "
                        f"{increase:.1%} exceeds {VOLUME_HARD_LIMIT_PCT:.0%} hard limit "
                        f"({volumes[i - 1]:.1f}km \u2192 {volumes[i]:.1f}km)"
                    )
                elif increase > VOLUME_WARNING_THRESHOLD_PCT:
                    warnings.append(
                        f"Week {i} to {i + 1}: volume increase "
                        f"{increase:.1%} exceeds {VOLUME_WARNING_THRESHOLD_PCT:.0%} guideline "
                        f"({volumes[i - 1]:.1f}km \u2192 {volumes[i]:.1f}km)"
                    )

        # Check return_to_run has no quality workouts
        if plan.goal_type.value == "return_to_run":
            for w in plan.workouts:
                if w.workout_type.value in _RETURN_TO_RUN_PROHIBITED_TYPES:
                    errors.append(
                        f"return_to_run plan contains prohibited workout type "
                        f"'{w.workout_type.value}' in week {w.week_number}"
                    )

        # Check workout dates align with plan start_date + week offsets
        if plan.start_date:
            from datetime import timedelta

            for w in plan.workouts:
                if w.workout_date is not None:
                    expected_week_start = plan.start_date + timedelta(
                        weeks=w.week_number - 1
                    )
                    expected_week_end = expected_week_start + timedelta(days=6)
                    if not (expected_week_start <= w.workout_date <= expected_week_end):
                        errors.append(
                            f"Workout {w.workout_id} date {w.workout_date} "
                            f"is outside week {w.week_number} range "
                            f"({expected_week_start} - {expected_week_end})"
                        )

        return errors, warnings

    async def _get_training_plan(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.database.readers.training_plans import TrainingPlanReader

        try:
            reader = TrainingPlanReader(db_path=str(self._db_reader.db_path))
            plan_id = arguments["plan_id"]
            version = arguments.get("version")
            week_number = arguments.get("week_number")
            summary_only = arguments.get("summary_only", False)

            result = reader.get_training_plan(
                plan_id=plan_id,
                version=version,
                week_number=week_number,
                summary_only=summary_only,
            )
        except Exception as e:
            logger.error(f"Get training plan failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    async def _upload_workout_to_garmin(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader

        try:
            uploader = GarminWorkoutUploader(db_path=str(self._db_reader.db_path))
            schedule = arguments.get("schedule", True)

            if "workout_id" in arguments:
                result = uploader.upload_workout(
                    arguments["workout_id"], schedule=schedule
                )
            elif "plan_id" in arguments:
                week_number = arguments.get("week_number")
                result = uploader.upload_plan_workouts(
                    arguments["plan_id"],
                    week_number=week_number,
                    schedule=schedule,
                )
            else:
                result = {"error": "Either workout_id or plan_id is required"}
        except Exception as e:
            logger.error(f"Garmin upload failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    async def _delete_workout_from_garmin(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader

        try:
            uploader = GarminWorkoutUploader(db_path=str(self._db_reader.db_path))

            if "workout_id" in arguments:
                result = uploader.delete_workout(arguments["workout_id"])
            elif "plan_id" in arguments:
                week_number = arguments.get("week_number")
                result = uploader.delete_plan_workouts(
                    arguments["plan_id"],
                    week_number=week_number,
                )
            else:
                result = {"error": "Either workout_id or plan_id is required"}
        except Exception as e:
            logger.error(f"Garmin delete failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]
