"""
Garmin DB MCP Server

Provides efficient DuckDB access to performance data via MCP protocol.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tools.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)

# Initialize server
mcp = Server("garmin-db")
db_reader = GarminDBReader()


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available DuckDB query tools."""
    return [
        Tool(
            name="get_section_analysis",
            description="Get section analysis data from DuckDB",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "section_type": {"type": "string"},
                },
                "required": ["activity_id", "section_type"],
            },
        ),
        Tool(
            name="get_activity_by_date",
            description="Get activity ID and metadata from date",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                },
                "required": ["date"],
            },
        ),
        Tool(
            name="get_date_by_activity_id",
            description="Get date and activity name from activity ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_pace_hr",
            description="Get pace and heart rate data from splits (lightweight: ~3 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_form_metrics",
            description="Get form efficiency metrics from splits (lightweight: ~4 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_elevation",
            description="Get elevation and terrain data from splits (lightweight: ~5 fields/split)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="insert_section_analysis_dict",
            description="Insert section analysis dict directly into DuckDB (no file creation)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "activity_date": {"type": "string"},
                    "section_type": {"type": "string"},
                    "analysis_data": {"type": "object"},
                },
                "required": [
                    "activity_id",
                    "activity_date",
                    "section_type",
                    "analysis_data",
                ],
            },
        ),
        Tool(
            name="get_form_efficiency_summary",
            description="Get form efficiency summary (GCT, VO, VR metrics) from form_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_hr_efficiency_analysis",
            description="Get HR efficiency analysis (zone distribution, training type) from hr_efficiency table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_heart_rate_zones_detail",
            description="Get heart rate zones detail (boundaries, time distribution) from heart_rate_zones table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_vo2_max_data",
            description="Get VO2 max data (precise value, fitness age, category) from vo2_max table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_lactate_threshold_data",
            description="Get lactate threshold data (HR, speed, power) from lactate_threshold table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_performance_trends",
            description="Get performance trends data (pace consistency, HR drift, phase analysis)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_weather_data",
            description="Get weather data (temperature, humidity, wind) from activity",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_all",
            description="Get all split data (all 22 fields) from splits table",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_interval_analysis",
            description="Analyze interval training Work/Recovery segments using intensity_type from DuckDB",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_split_time_series_detail",
            description="Get second-by-second detailed metrics for a specific 1km split (DuckDB-based, 98.8% token reduction)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "split_number": {
                        "type": "integer",
                        "description": "Split number (1-based)",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metric names to extract (optional)",
                    },
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, only return statistics (98.8% token reduction). Default: false",
                    },
                    "detect_anomalies": {
                        "type": "boolean",
                        "description": "Whether to detect anomalies in the data. Default: false",
                    },
                    "z_threshold": {
                        "type": "number",
                        "description": "Z-score threshold for anomaly detection. Default: 2.0",
                    },
                },
                "required": ["activity_id", "split_number"],
            },
        ),
        Tool(
            name="get_time_range_detail",
            description="Get second-by-second detailed metrics for arbitrary time range",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "start_time_s": {
                        "type": "integer",
                        "description": "Start time in seconds",
                    },
                    "end_time_s": {
                        "type": "integer",
                        "description": "End time in seconds",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metric names to extract (optional)",
                    },
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, only return statistics (mean, std, min, max) without time series data. Default: false",
                    },
                },
                "required": ["activity_id", "start_time_s", "end_time_s"],
            },
        ),
        Tool(
            name="detect_form_anomalies_summary",
            description="Detect form anomalies and return lightweight summary (~700 tokens, 95% reduction)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metrics to analyze (default: GCT, VO, VR)",
                    },
                    "z_threshold": {
                        "type": "number",
                        "description": "Z-score threshold for anomaly detection (default: 2.0)",
                    },
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_form_anomaly_details",
            description="Get detailed anomaly information with flexible filtering (variable token size)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "anomaly_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional specific anomaly IDs to retrieve",
                    },
                    "time_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Optional [start_sec, end_sec] time range",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional metric names to filter",
                    },
                    "z_threshold": {
                        "type": "number",
                        "description": "Optional minimum z-score threshold",
                    },
                    "causes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional causes to filter (elevation_change, pace_change, fatigue)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order: z_score (desc) or timestamp (asc)",
                        "enum": ["z_score", "timestamp"],
                        "default": "z_score",
                    },
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="analyze_performance_trends",
            description="Analyze performance trends across multiple activities with filtering (Phase 3.1)",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "Metric name (pace, heart_rate, cadence, power, vertical_oscillation, "
                        "ground_contact_time, vertical_ratio, distance, training_effect, elevation_gain)",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format",
                    },
                    "activity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of activity IDs to analyze",
                    },
                    "activity_type": {
                        "type": "string",
                        "description": "Optional activity type filter",
                    },
                    "temperature_range": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Optional [min_temp, max_temp] filter in Celsius",
                    },
                    "distance_range": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Optional [min_km, max_km] filter",
                    },
                },
                "required": ["metric", "start_date", "end_date", "activity_ids"],
            },
        ),
        Tool(
            name="extract_insights",
            description="Extract insights from section analyses using keyword-based search (Phase 3.2)",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords to search for (e.g., improvements, concerns, patterns)",
                    },
                    "section_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional section types to filter by",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of results to skip (default: 0)",
                        "default": 0,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum token count (optional)",
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="classify_activity_type",
            description="Classify activity type based on HR zones, distance, and power (Phase 3.3)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="compare_similar_workouts",
            description="Find and compare similar past workouts based on pace and distance (Phase 4.5)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "Target activity ID",
                    },
                    "pace_tolerance": {
                        "type": "number",
                        "description": "Pace tolerance as fraction (default 0.1 = ±10%)",
                    },
                    "distance_tolerance": {
                        "type": "number",
                        "description": "Distance tolerance as fraction (default 0.1 = ±10%)",
                    },
                    "terrain_match": {
                        "type": "boolean",
                        "description": "Whether to match terrain characteristics",
                    },
                    "activity_type_filter": {
                        "type": "string",
                        "description": "Optional activity type keyword filter",
                    },
                    "date_range": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional [start_date, end_date] in YYYY-MM-DD format",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 10)",
                    },
                },
                "required": ["activity_id"],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    import json

    if name == "get_section_analysis":
        activity_id = arguments["activity_id"]
        section_type = arguments["section_type"]
        result = db_reader.get_section_analysis(activity_id, section_type)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_activity_by_date":
        date = arguments["date"]
        import duckdb

        try:
            # Query activities table for given date
            conn = duckdb.connect(str(db_reader.db_path), read_only=True)
            activities_result = conn.execute(
                """
                SELECT
                    activity_id,
                    activity_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds
                FROM activities
                WHERE date = ?
                ORDER BY start_time_local
                """,
                [date],
            ).fetchall()
            conn.close()

            activities = [
                {
                    "activity_id": row[0],
                    "activity_name": row[1],
                    "start_time": str(row[2]) if row[2] else None,
                    "distance_km": row[3],
                    "duration_seconds": row[4],
                }
                for row in activities_result
            ]

            if len(activities) == 0:
                result = {
                    "success": False,
                    "error": f"No activities found for {date}",
                    "activities": [],
                }
            elif len(activities) == 1:
                result = {
                    "success": True,
                    "activity_id": activities[0]["activity_id"],
                    "activity_name": activities[0]["activity_name"],
                    "start_time": activities[0]["start_time"],
                    "distance_km": activities[0]["distance_km"],
                    "duration_seconds": activities[0]["duration_seconds"],
                }
            else:
                result = {
                    "success": False,
                    "error": f"Multiple activities found for {date}. Please specify activity_id.",
                    "activities": activities,
                }

        except Exception as e:
            result = {"success": False, "error": str(e), "activities": []}

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_date_by_activity_id":
        activity_id = arguments["activity_id"]
        date = db_reader.get_activity_date(activity_id)
        result = {"activity_id": activity_id, "date": date}
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_pace_hr":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_pace_hr(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_form_metrics":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_form_metrics(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_elevation":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_elevation(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "insert_section_analysis_dict":
        from tools.database.inserters.section_analyses import insert_section_analysis

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

    elif name == "get_form_efficiency_summary":
        activity_id = arguments["activity_id"]
        result = db_reader.get_form_efficiency_summary(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_hr_efficiency_analysis":
        activity_id = arguments["activity_id"]
        result = db_reader.get_hr_efficiency_analysis(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_heart_rate_zones_detail":
        activity_id = arguments["activity_id"]
        result = db_reader.get_heart_rate_zones_detail(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_vo2_max_data":
        activity_id = arguments["activity_id"]
        result = db_reader.get_vo2_max_data(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_lactate_threshold_data":
        activity_id = arguments["activity_id"]
        result = db_reader.get_lactate_threshold_data(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_performance_trends":
        activity_id = arguments["activity_id"]
        result = db_reader.get_performance_trends(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_weather_data":
        activity_id = arguments["activity_id"]
        result = db_reader.get_weather_data(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_splits_all":
        activity_id = arguments["activity_id"]
        result = db_reader.get_splits_all(activity_id)
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_interval_analysis":
        from tools.rag.queries.interval_analysis import IntervalAnalyzer

        analyzer = IntervalAnalyzer()
        result = analyzer.get_interval_analysis(
            activity_id=arguments["activity_id"],
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_split_time_series_detail":
        from tools.rag.queries.time_series_detail import TimeSeriesDetailExtractor

        extractor = TimeSeriesDetailExtractor()
        result = extractor.get_split_time_series_detail(
            activity_id=arguments["activity_id"],
            split_number=arguments["split_number"],
            metrics=arguments.get("metrics"),
            statistics_only=arguments.get("statistics_only", False),
            detect_anomalies=arguments.get("detect_anomalies", False),
            z_threshold=arguments.get("z_threshold", 2.0),
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "get_time_range_detail":
        from tools.rag.queries.time_series_detail import TimeSeriesDetailExtractor

        extractor = TimeSeriesDetailExtractor()
        result = extractor.extract_metrics(
            activity_id=arguments["activity_id"],
            start_time=arguments["start_time_s"],
            end_time=arguments["end_time_s"],
            metrics=arguments.get("metrics"),
            statistics_only=arguments.get("statistics_only", False),
        )
        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "detect_form_anomalies_summary":
        from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector

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

    elif name == "get_form_anomaly_details":
        from tools.rag.queries.form_anomaly_detector import FormAnomalyDetector

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

    elif name == "analyze_performance_trends":
        from tools.rag.queries.trends import PerformanceTrendAnalyzer

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

    elif name == "extract_insights":
        from tools.rag.queries.insights import InsightExtractor

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

    elif name == "classify_activity_type":
        from tools.rag.utils.activity_classifier import ActivityClassifier

        classifier = ActivityClassifier()
        activity_id = arguments["activity_id"]

        # Get HR zones data and activity metadata
        hr_zones_data = db_reader.get_heart_rate_zones_detail(activity_id)

        # Get distance from activities table
        import duckdb

        try:
            conn = duckdb.connect(str(db_reader.db_path), read_only=True)
            activity_result = conn.execute(
                """
                SELECT total_distance_km
                FROM activities
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()
            conn.close()

            distance_km = activity_result[0] if activity_result else 0.0
        except Exception:
            distance_km = 0.0

        # Get average power from splits (optional)
        splits = db_reader.get_splits_all(activity_id)
        avg_power = None
        if splits and splits.get("splits"):
            power_values = [s.get("power") for s in splits["splits"] if s.get("power")]
            if power_values:
                import numpy as np

                # Filter out None values and convert to float list
                power_floats = [float(p) for p in power_values if p is not None]
                avg_power = float(np.mean(power_floats)) if power_floats else None

        # Classify activity
        result = classifier.classify(
            hr_zones_data=hr_zones_data,
            distance_km=distance_km,
            avg_power=avg_power,
        )

        # Add activity_id to result
        result["activity_id"] = activity_id

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    elif name == "compare_similar_workouts":
        from tools.rag.queries.comparisons import WorkoutComparator

        comparator = WorkoutComparator()
        activity_id = arguments["activity_id"]
        pace_tolerance = arguments.get("pace_tolerance", 0.1)
        distance_tolerance = arguments.get("distance_tolerance", 0.1)
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
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
