"""Handler for training plan tool calls."""

import json
import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class TrainingPlanHandler:
    """Handles training plan-related tool calls."""

    _tool_names: set[str] = {
        "get_current_fitness_summary",
        "generate_training_plan",
        "get_training_plan",
        "upload_workout_to_garmin",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_current_fitness_summary":
            return await self._get_current_fitness_summary(arguments)
        elif name == "generate_training_plan":
            return await self._generate_training_plan(arguments)
        elif name == "get_training_plan":
            return await self._get_training_plan(arguments)
        elif name == "upload_workout_to_garmin":
            return await self._upload_workout_to_garmin(arguments)
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

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _generate_training_plan(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        try:
            generator = TrainingPlanGenerator(db_path=str(self._db_reader.db_path))
            plan = generator.generate(
                goal_type=arguments["goal_type"],
                total_weeks=arguments["total_weeks"],
                target_race_date=arguments.get("target_race_date"),
                target_time_seconds=arguments.get("target_time_seconds"),
                runs_per_week=arguments.get("runs_per_week", 4),
                preferred_long_run_day=arguments.get("preferred_long_run_day", 7),
            )
            result = plan.to_summary()
            result["first_week_workouts"] = [
                w.model_dump() for w in plan.get_week_workouts(1)
            ]
        except Exception as e:
            logger.error(f"Plan generation failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False, default=str),
            )
        ]

    async def _get_training_plan(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.database.readers.training_plans import TrainingPlanReader

        try:
            reader = TrainingPlanReader(db_path=str(self._db_reader.db_path))
            plan_id = arguments["plan_id"]
            week_number = arguments.get("week_number")
            summary_only = arguments.get("summary_only", False)

            result = reader.get_training_plan(
                plan_id=plan_id,
                week_number=week_number,
                summary_only=summary_only,
            )
        except Exception as e:
            logger.error(f"Get training plan failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False, default=str),
            )
        ]

    async def _upload_workout_to_garmin(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader

        try:
            uploader = GarminWorkoutUploader(db_path=str(self._db_reader.db_path))

            if "workout_id" in arguments:
                result = uploader.upload_workout(arguments["workout_id"])
            elif "plan_id" in arguments:
                week_number = arguments.get("week_number")
                result = uploader.upload_plan_workouts(
                    arguments["plan_id"], week_number=week_number
                )
            else:
                result = {"error": "Either workout_id or plan_id is required"}
        except Exception as e:
            logger.error(f"Garmin upload failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False, default=str),
            )
        ]
