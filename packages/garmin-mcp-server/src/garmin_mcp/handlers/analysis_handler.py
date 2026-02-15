"""Handler for analysis tools."""

import json
import logging
from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class AnalysisHandler:
    """Handles analysis-related tool calls."""

    _tool_names: set[str] = {
        "insert_section_analysis_dict",
        "get_interval_analysis",
        "detect_form_anomalies_summary",
        "get_form_anomaly_details",
        "analyze_performance_trends",
        "extract_insights",
        "compare_similar_workouts",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "insert_section_analysis_dict":
            return await self._insert_section_analysis_dict(arguments)
        elif name == "get_interval_analysis":
            return await self._get_interval_analysis(arguments)
        elif name == "detect_form_anomalies_summary":
            return await self._detect_form_anomalies_summary(arguments)
        elif name == "get_form_anomaly_details":
            return await self._get_form_anomaly_details(arguments)
        elif name == "analyze_performance_trends":
            return await self._analyze_performance_trends(arguments)
        elif name == "extract_insights":
            return await self._extract_insights(arguments)
        elif name == "compare_similar_workouts":
            return await self._compare_similar_workouts(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")

    async def _insert_section_analysis_dict(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.database.inserters.section_analyses import (
            insert_section_analysis,
        )

        activity_id = arguments["activity_id"]
        activity_date = arguments["activity_date"]
        section_type = arguments["section_type"]
        analysis_data = arguments["analysis_data"]

        success = insert_section_analysis(
            activity_id=activity_id,
            activity_date=activity_date,
            section_type=section_type,
            analysis_data=analysis_data,
        )

        result = {
            "success": success,
            "activity_id": activity_id,
            "section_type": section_type,
        }

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _get_interval_analysis(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.interval_analysis import IntervalAnalyzer

        analyzer = IntervalAnalyzer()
        result = analyzer.get_interval_analysis(
            activity_id=arguments["activity_id"],
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _detect_form_anomalies_summary(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector

        detector = FormAnomalyDetector()
        result = detector.detect_form_anomalies_summary(
            activity_id=arguments["activity_id"],
            metrics=arguments.get("metrics"),
            z_threshold=arguments.get("z_threshold", 2.0),
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _get_form_anomaly_details(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector

        detector = FormAnomalyDetector()

        # Build filters dict from MCP arguments
        filters: dict[str, Any] = {}

        if "anomaly_ids" in arguments:
            filters["anomaly_ids"] = arguments["anomaly_ids"]

        if "time_range" in arguments:
            filters["time_range"] = tuple(arguments["time_range"])

        if "metrics" in arguments:
            filters["metrics"] = arguments["metrics"]

        if "z_threshold" in arguments:
            filters["min_z_score"] = arguments["z_threshold"]

        if "causes" in arguments:
            filters["causes"] = arguments["causes"]

        # Always set limit (default: 50)
        filters["limit"] = arguments.get("limit", 50)

        result = detector.get_form_anomaly_details(
            activity_id=arguments["activity_id"],
            metrics=arguments.get("metrics"),
            z_threshold=arguments.get("z_threshold", 2.0),
            filters=filters if filters else None,
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _analyze_performance_trends(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer

        trend_analyzer = PerformanceTrendAnalyzer()

        # Convert temperature_range and distance_range from list to tuple if provided
        temperature_range = arguments.get("temperature_range")
        if temperature_range is not None:
            temperature_range = tuple(temperature_range)

        distance_range = arguments.get("distance_range")
        if distance_range is not None:
            distance_range = tuple(distance_range)

        result = trend_analyzer.analyze_metric_trend(
            metric=arguments["metric"],
            start_date=arguments["start_date"],
            end_date=arguments["end_date"],
            activity_ids=arguments["activity_ids"],
            activity_type=arguments.get("activity_type"),
            temperature_range=temperature_range,
            distance_range=distance_range,
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _extract_insights(self, arguments: dict[str, Any]) -> list[TextContent]:
        from garmin_mcp.rag.queries.insights import InsightExtractor

        insight_extractor = InsightExtractor()

        # Check if this is a single-activity extraction or a general search
        if "activity_id" in arguments:
            # Single activity insight extraction with token limiting
            result = insight_extractor.extract_insights(  # type: ignore[assignment]
                activity_id=arguments["activity_id"],
                keywords=arguments["keywords"],
                max_tokens=arguments.get("max_tokens"),
            )
        else:
            # General keyword-based search with pagination
            result = insight_extractor.search_by_keywords(  # type: ignore[assignment]
                keywords=arguments["keywords"],
                section_types=arguments.get("section_types"),
                limit=arguments.get("limit", 10),
                offset=arguments.get("offset", 0),
            )

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    async def _compare_similar_workouts(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from garmin_mcp.rag.queries.comparisons import WorkoutComparator

        comparator = WorkoutComparator()
        activity_id = arguments["activity_id"]
        pace_tolerance = arguments.get("pace_tolerance", 0.2)
        distance_tolerance = arguments.get("distance_tolerance", 0.2)
        terrain_match = arguments.get("terrain_match", False)
        activity_type_filter = arguments.get("activity_type_filter")
        date_range_list = arguments.get("date_range")
        date_range = tuple(date_range_list) if date_range_list else None
        limit = arguments.get("limit", 10)

        result = comparator.find_similar_workouts(
            activity_id=activity_id,
            pace_tolerance=pace_tolerance,
            distance_tolerance=distance_tolerance,
            terrain_match=terrain_match,
            activity_type_filter=activity_type_filter,
            date_range=date_range,
            limit=limit,
        )

        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False, default=str),
            )
        ]
