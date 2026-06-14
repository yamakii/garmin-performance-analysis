"""Handler for athlete profile tool calls."""

import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response

logger = logging.getLogger(__name__)


class AthleteHandler:
    """Handles athlete profile-related tool calls."""

    _tool_names: set[str] = {
        "save_athlete_profile",
        "get_athlete_profile",
        "save_weekly_review",
        "get_weekly_review",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "save_athlete_profile":
            return await self._save_athlete_profile(arguments)
        elif name == "get_athlete_profile":
            return await self._get_athlete_profile(arguments)
        elif name == "save_weekly_review":
            return await self._save_weekly_review(arguments)
        elif name == "get_weekly_review":
            return await self._get_weekly_review(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def _save_athlete_profile(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.database.inserters.athlete import insert_athlete_profile

        try:
            profile = arguments["profile"]
            insert_athlete_profile(
                profile=profile,
                db_path=str(self._db_reader.db_path),
            )
            result: dict[str, Any] = {
                "status": "saved",
                "user_id": profile.get("user_id", "default"),
                "goal_count": len(profile.get("goals") or []),
                "retrospective_count": len(profile.get("retrospectives") or []),
            }
        except Exception as e:
            logger.error(f"Save athlete profile failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    async def _get_athlete_profile(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.database.readers.athlete import AthleteReader

        try:
            reader = AthleteReader(db_path=str(self._db_reader.db_path))
            user_id = arguments.get("user_id", "default")
            result = reader.get_athlete_profile(user_id=user_id)
        except Exception as e:
            logger.error(f"Get athlete profile failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    async def _save_weekly_review(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.database.inserters.athlete import insert_weekly_review

        try:
            review = arguments["review"]
            insert_weekly_review(
                review=review,
                db_path=str(self._db_reader.db_path),
            )
            result: dict[str, Any] = {
                "status": "saved",
                "user_id": review.get("user_id", "default"),
                "week_start_date": review.get("week_start_date"),
            }
        except Exception as e:
            logger.error(f"Save weekly review failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]

    async def _get_weekly_review(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.database.readers.athlete import AthleteReader

        try:
            reader = AthleteReader(db_path=str(self._db_reader.db_path))
            user_id = arguments.get("user_id", "default")
            result = reader.get_weekly_review(
                week_start_date=arguments.get("week_start_date"),
                user_id=user_id,
            )
        except Exception as e:
            logger.error(f"Get weekly review failed: {e}")
            result = {"error": str(e)}

        return [
            TextContent(
                type="text",
                text=format_json_response(result, default=str),
            )
        ]
