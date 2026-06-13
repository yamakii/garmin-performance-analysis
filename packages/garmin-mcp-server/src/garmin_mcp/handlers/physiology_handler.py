"""Handler for physiology tools."""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response


class PhysiologyHandler:
    """Handles physiology-related tool calls."""

    _tool_names: set[str] = {
        "get_form_efficiency_summary",
        "get_form_evaluations",
        "get_form_baseline_trend",
        "get_hr_efficiency_analysis",
        "get_heart_rate_zones_detail",
        "get_vo2_max_data",
        "get_lactate_threshold_data",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_form_baseline_trend":
            return await self._get_form_baseline_trend(arguments)

        activity_id = arguments["activity_id"]

        if name == "get_form_efficiency_summary":
            result = self._db_reader.get_form_efficiency_summary(activity_id)  # type: ignore[assignment]
        elif name == "get_form_evaluations":
            result = self._db_reader.get_form_evaluations(activity_id)  # type: ignore[assignment]
        elif name == "get_hr_efficiency_analysis":
            result = self._db_reader.get_hr_efficiency_analysis(activity_id)  # type: ignore[assignment]
        elif name == "get_heart_rate_zones_detail":
            result = self._db_reader.get_heart_rate_zones_detail(activity_id)  # type: ignore[assignment]
        elif name == "get_vo2_max_data":
            result = self._db_reader.get_vo2_max_data(activity_id)  # type: ignore[assignment]
        elif name == "get_lactate_threshold_data":
            result = self._db_reader.get_lactate_threshold_data(activity_id)  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=format_json_response(result))]

    async def _get_form_baseline_trend(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        activity_id = arguments["activity_id"]
        activity_date = arguments["activity_date"]
        user_id = arguments.get("user_id", "default")
        condition_group = arguments.get("condition_group", "flat_road")

        result = self._db_reader.physiology.get_form_baseline_trend(
            activity_id,
            activity_date,
            user_id=user_id,
            condition_group=condition_group,
        )

        return [TextContent(type="text", text=format_json_response(result))]
