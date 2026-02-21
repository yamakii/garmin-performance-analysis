"""Handler for time series tools: get_split_time_series_detail, get_time_range_detail."""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response


class TimeSeriesHandler:
    """Handles time-series-related tool calls."""

    _tool_names: set[str] = {"get_split_time_series_detail", "get_time_range_detail"}

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_split_time_series_detail":
            return await self._get_split_time_series_detail(arguments)
        elif name == "get_time_range_detail":
            return await self._get_time_range_detail(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def _get_split_time_series_detail(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.time_series_detail import TimeSeriesDetailExtractor

        extractor = TimeSeriesDetailExtractor()
        result = extractor.get_split_time_series_detail(
            activity_id=arguments["activity_id"],
            split_number=arguments["split_number"],
            metrics=arguments.get("metrics"),
            statistics_only=arguments.get("statistics_only", False),
            detect_anomalies=arguments.get("detect_anomalies", False),
            z_threshold=arguments.get("z_threshold", 2.0),
        )
        return [TextContent(type="text", text=format_json_response(result))]

    async def _get_time_range_detail(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.time_series_detail import TimeSeriesDetailExtractor

        extractor = TimeSeriesDetailExtractor()
        result = extractor.extract_metrics(
            activity_id=arguments["activity_id"],
            start_time=arguments["start_time_s"],
            end_time=arguments["end_time_s"],
            metrics=arguments.get("metrics"),
            statistics_only=arguments.get("statistics_only", False),
        )
        return [TextContent(type="text", text=format_json_response(result))]
