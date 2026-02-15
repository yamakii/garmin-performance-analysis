"""
Garmin DB MCP Server

Provides efficient DuckDB access to performance data via MCP protocol.
"""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.analysis_handler import AnalysisHandler
from garmin_mcp.handlers.base import ToolHandler
from garmin_mcp.handlers.export_handler import ExportHandler
from garmin_mcp.handlers.metadata_handler import MetadataHandler
from garmin_mcp.handlers.performance_handler import PerformanceHandler
from garmin_mcp.handlers.physiology_handler import PhysiologyHandler
from garmin_mcp.handlers.splits_handler import SplitsHandler
from garmin_mcp.handlers.time_series_handler import TimeSeriesHandler
from garmin_mcp.handlers.training_plan_handler import TrainingPlanHandler

logger = logging.getLogger(__name__)

# Initialize server
mcp = Server("garmin-db")
db_reader = GarminDBReader()

# Registry of handlers (lazily initialized)
_handlers: list[ToolHandler] = []


def _init_handlers() -> None:
    """Initialize handler registry with db_reader instance."""
    global _handlers
    _handlers = [
        MetadataHandler(db_reader),
        SplitsHandler(db_reader),
        PhysiologyHandler(db_reader),
        PerformanceHandler(db_reader),
        AnalysisHandler(db_reader),
        TimeSeriesHandler(db_reader),
        ExportHandler(db_reader),
        TrainingPlanHandler(db_reader),
    ]


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List available DuckDB query tools."""
    return [
        Tool(
            name="export",
            description="Export query results to file (returns handle only, not data). Use for large datasets that need processing in Python.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "DuckDB SQL query to execute",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["parquet", "csv"],
                        "description": "Output format (parquet recommended for efficiency)",
                        "default": "parquet",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Safety limit for export size (default: 100000)",
                        "default": 100000,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_section_analysis",
            description="Get section analysis data from DuckDB (DEPRECATED: Use extract_insights() for summarized data)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "section_type": {"type": "string"},
                    "max_output_size": {
                        "type": "integer",
                        "description": "Maximum output size in bytes (default: 10240). Set to null for no limit.",
                        "default": 10240,
                    },
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
            description="Get pace and heart rate data from splits (lightweight: ~3 fields/split, or ~200 bytes with statistics_only=True)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, return only aggregated statistics (mean, median, std, min, max) instead of per-split data. Reduces output size by ~80%. Default: false",
                        "default": False,
                    },
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_form_metrics",
            description="Get form efficiency metrics from splits (lightweight: ~4 fields/split, or ~300 bytes with statistics_only=True)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, return only aggregated statistics (mean, median, std, min, max) for GCT, VO, VR instead of per-split data. Reduces output size by ~80%. Default: false",
                        "default": False,
                    },
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_elevation",
            description="Get elevation and terrain data from splits (lightweight: ~5 fields/split, or ~250 bytes with statistics_only=True)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, return only aggregated statistics (mean, median, std, min, max) for elevation gain/loss instead of per-split data. Reduces output size by ~80%. Default: false",
                        "default": False,
                    },
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_splits_comprehensive",
            description="Get comprehensive split data (12 fields: pace, HR, form, power, cadence, elevation). Supports statistics_only mode for 67% token reduction.",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "statistics_only": {
                        "type": "boolean",
                        "description": "If true, return only aggregated statistics (mean, median, std, min, max) instead of per-split data. Reduces output size by ~67%. Default: false",
                        "default": False,
                    },
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
            name="get_form_evaluations",
            description="Get pace-corrected form evaluation results (expected values, actual values, scores, star ratings, evaluation texts)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                },
                "required": ["activity_id"],
            },
        ),
        Tool(
            name="get_form_baseline_trend",
            description="Get form baseline trend (1-month coefficient comparison for form_trend analysis)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "activity_date": {
                        "type": "string",
                        "description": "Activity date in YYYY-MM-DD format",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID (default: 'default')",
                        "default": "default",
                    },
                    "condition_group": {
                        "type": "string",
                        "description": "Condition group (default: 'flat_road')",
                        "default": "flat_road",
                    },
                },
                "required": ["activity_id", "activity_date"],
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
            description="Get all split data (all 22 fields) from splits table (DEPRECATED: Use export() or lightweight splits functions)",
            inputSchema={
                "type": "object",
                "properties": {
                    "activity_id": {"type": "integer"},
                    "max_output_size": {
                        "type": "integer",
                        "description": "Maximum output size in bytes (default: 10240). Set to null for no limit.",
                        "default": 10240,
                    },
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
                        "description": "Pace tolerance as fraction (default 0.2 = ±20%)",
                    },
                    "distance_tolerance": {
                        "type": "number",
                        "description": "Distance tolerance as fraction (default 0.2 = ±20%)",
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
        # --- Training Plan Tools ---
        Tool(
            name="get_current_fitness_summary",
            description="Get current fitness level assessment (VDOT, pace zones, weekly volume, training type distribution)",
            inputSchema={
                "type": "object",
                "properties": {
                    "lookback_weeks": {
                        "type": "integer",
                        "description": "Number of weeks to analyze (default: 8)",
                    },
                },
            },
        ),
        Tool(
            name="generate_training_plan",
            description="Generate a personalized training plan with periodization and pace targets",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal_type": {
                        "type": "string",
                        "enum": [
                            "race_5k",
                            "race_10k",
                            "race_half",
                            "race_full",
                            "fitness",
                        ],
                        "description": "Training goal type",
                    },
                    "total_weeks": {
                        "type": "integer",
                        "description": "Plan duration in weeks (4-24)",
                    },
                    "target_race_date": {
                        "type": "string",
                        "description": "Race date in YYYY-MM-DD format (for race goals)",
                    },
                    "target_time_seconds": {
                        "type": "integer",
                        "description": "Target race time in seconds (optional)",
                    },
                    "runs_per_week": {
                        "type": "integer",
                        "description": "Number of runs per week (3-6, default: 4)",
                    },
                    "preferred_long_run_day": {
                        "type": "integer",
                        "description": "Preferred long run day (1=Mon, 7=Sun, default: 7)",
                    },
                },
                "required": ["goal_type", "total_weeks"],
            },
        ),
        Tool(
            name="get_training_plan",
            description="Get a previously generated training plan",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan_id": {
                        "type": "string",
                        "description": "Plan identifier",
                    },
                    "week_number": {
                        "type": "integer",
                        "description": "Specific week to retrieve (optional)",
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "If true, exclude individual workouts (default: false)",
                    },
                },
                "required": ["plan_id"],
            },
        ),
        Tool(
            name="upload_workout_to_garmin",
            description="Upload workout(s) to Garmin Connect",
            inputSchema={
                "type": "object",
                "properties": {
                    "workout_id": {
                        "type": "string",
                        "description": "Single workout ID to upload",
                    },
                    "plan_id": {
                        "type": "string",
                        "description": "Plan ID to upload all workouts from",
                    },
                    "week_number": {
                        "type": "integer",
                        "description": "Specific week to upload (with plan_id)",
                    },
                },
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls by dispatching to the appropriate handler."""
    if not _handlers:
        _init_handlers()
    for handler in _handlers:
        if handler.handles(name):
            return await handler.handle(name, arguments)
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Main entry point for MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def run() -> None:
    """Console script entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
