"""
Tool schema definitions for the Garmin DB MCP Server.

Each tool is defined as a dict with name, description, and inputSchema.
The get_tool_definitions() function returns MCP Tool objects.
"""

from mcp.types import Tool

# ============================================================
# Schema definitions grouped by category
# ============================================================

_EXPORT_TOOLS: list[dict] = [
    {
        "name": "export",
        "description": "Export query results to file (returns handle only, not data). Use for large datasets that need processing in Python.",
        "inputSchema": {
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
    },
]

_METADATA_TOOLS: list[dict] = [
    {
        "name": "get_activity_by_date",
        "description": "Get activity ID and metadata from date",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_date_by_activity_id",
        "description": "Get date and activity name from activity ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "ingest_activity",
        "description": "Ingest activity data from Garmin Connect into DuckDB. Fetches raw data, stores in DuckDB, and runs form evaluation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Activity date in YYYY-MM-DD format",
                },
                "force_regenerate": {
                    "type": "boolean",
                    "description": "Force regeneration of all data (default: false)",
                    "default": False,
                },
            },
            "required": ["date"],
        },
    },
]

_SPLITS_TOOLS: list[dict] = [
    {
        "name": "get_splits_pace_hr",
        "description": "Get pace and heart rate data from splits (lightweight: ~3 fields/split, or ~200 bytes with statistics_only=True)",
        "inputSchema": {
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
    },
    {
        "name": "get_splits_form_metrics",
        "description": "Get form efficiency metrics from splits (lightweight: ~4 fields/split, or ~300 bytes with statistics_only=True)",
        "inputSchema": {
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
    },
    {
        "name": "get_splits_elevation",
        "description": "Get elevation and terrain data from splits (lightweight: ~5 fields/split, or ~250 bytes with statistics_only=True)",
        "inputSchema": {
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
    },
    {
        "name": "get_splits_comprehensive",
        "description": "Get comprehensive split data (12 fields: pace, HR, form, power, cadence, elevation). Supports statistics_only mode for 67% token reduction.",
        "inputSchema": {
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
    },
    {
        "name": "get_interval_analysis",
        "description": "Analyze interval training Work/Recovery segments using intensity_type from DuckDB",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
]

_ANALYSIS_TOOLS: list[dict] = [
    {
        "name": "insert_section_analysis_dict",
        "description": "Insert section analysis dict directly into DuckDB (no file creation)",
        "inputSchema": {
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
    },
    {
        "name": "analyze_performance_trends",
        "description": "Analyze performance trends across multiple activities with filtering (Phase 3.1)",
        "inputSchema": {
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
    },
    {
        "name": "extract_insights",
        "description": "Extract insights from section analyses using keyword-based search (Phase 3.2)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords to search for (e.g., key_strengths, improvement_areas, efficiency, evaluation, environmental_impact)",
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
    },
    {
        "name": "compare_similar_workouts",
        "description": "Find and compare similar past workouts based on pace and distance (Phase 4.5)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {
                    "type": "integer",
                    "description": "Target activity ID",
                },
                "pace_tolerance": {
                    "type": "number",
                    "description": "Pace tolerance as fraction (default 0.2 = \u00b120%)",
                },
                "distance_tolerance": {
                    "type": "number",
                    "description": "Distance tolerance as fraction (default 0.2 = \u00b120%)",
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
    },
]

_PHYSIOLOGY_TOOLS: list[dict] = [
    {
        "name": "get_form_efficiency_summary",
        "description": "Get form efficiency summary (GCT, VO, VR metrics) from form_efficiency table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_form_evaluations",
        "description": "Get pace-corrected form evaluation results (expected values, actual values, scores, star ratings, evaluation texts)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_form_baseline_trend",
        "description": "Get form baseline trend (1-month coefficient comparison for form_trend analysis)",
        "inputSchema": {
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
    },
    {
        "name": "get_hr_efficiency_analysis",
        "description": "Get HR efficiency analysis (zone distribution, training type) from hr_efficiency table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_heart_rate_zones_detail",
        "description": "Get heart rate zones detail (boundaries, time distribution) from heart_rate_zones table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_vo2_max_data",
        "description": "Get VO2 max data (precise value, fitness age, category) from vo2_max table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_lactate_threshold_data",
        "description": "Get lactate threshold data (HR, speed, power) from lactate_threshold table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
]

_PERFORMANCE_TOOLS: list[dict] = [
    {
        "name": "get_performance_trends",
        "description": "Get performance trends data (pace consistency, HR drift, phase analysis)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_weather_data",
        "description": "Get weather data (temperature, humidity, wind) from activity",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "prefetch_activity_context",
        "description": "Pre-fetch shared activity context for analysis agents. Returns training_type, weather, terrain, HR efficiency (zone_percentages), form evaluation scores, phase structure, and planned workout in a single call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer"},
            },
            "required": ["activity_id"],
        },
    },
]

_TIME_SERIES_TOOLS: list[dict] = [
    {
        "name": "get_split_time_series_detail",
        "description": "Get second-by-second detailed metrics for a specific 1km split (DuckDB-based, 98.8% token reduction)",
        "inputSchema": {
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
    },
    {
        "name": "get_time_range_detail",
        "description": "Get second-by-second detailed metrics for arbitrary time range",
        "inputSchema": {
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
    },
    {
        "name": "detect_form_anomalies_summary",
        "description": "Detect form anomalies and return lightweight summary (~700 tokens, 95% reduction)",
        "inputSchema": {
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
    },
    {
        "name": "get_form_anomaly_details",
        "description": "Get detailed anomaly information with flexible filtering (variable token size)",
        "inputSchema": {
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
    },
]

_TRAINING_PLAN_TOOLS: list[dict] = [
    {
        "name": "get_current_fitness_summary",
        "description": "Get current fitness level assessment (VDOT, pace zones, weekly volume, training type distribution)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lookback_weeks": {
                    "type": "integer",
                    "description": "Number of weeks to analyze (default: 8)",
                },
            },
        },
    },
    {
        "name": "save_training_plan",
        "description": "Save a training plan (structured JSON) to DuckDB. Validates schema and safety constraints (volume progression <= 15%, return_to_run restrictions, date alignment).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "description": "TrainingPlan JSON conforming to the Pydantic model schema (plan_id, goal_type, vdot, pace_zones, total_weeks, start_date, weekly_volumes, phases, workouts, etc.)",
                },
            },
            "required": ["plan"],
        },
    },
    {
        "name": "get_training_plan",
        "description": "Get a previously generated training plan",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan identifier",
                },
                "version": {
                    "type": "integer",
                    "description": "Specific version to retrieve. Omit for latest active version.",
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
    },
    {
        "name": "upload_workout_to_garmin",
        "description": "Upload workout(s) to Garmin Connect",
        "inputSchema": {
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
                "schedule": {
                    "type": "boolean",
                    "description": "Schedule workouts on Garmin Connect calendar (default: true)",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "delete_workout_from_garmin",
        "description": "Delete workout(s) from Garmin Connect",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "Single workout ID to delete",
                },
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to delete all workouts from",
                },
                "week_number": {
                    "type": "integer",
                    "description": "Specific week to delete (with plan_id)",
                },
            },
        },
    },
]

_SERVER_TOOLS: list[dict] = [
    {
        "name": "reload_server",
        "description": "Restart the MCP server process to pick up code changes. The server will exit and Claude Code will automatically reconnect.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def get_tool_definitions() -> list[Tool]:
    """Return all MCP tool definitions as a list of Tool objects."""
    all_schemas = (
        _EXPORT_TOOLS
        + _METADATA_TOOLS
        + _SPLITS_TOOLS
        + _ANALYSIS_TOOLS
        + _PHYSIOLOGY_TOOLS
        + _PERFORMANCE_TOOLS
        + _TIME_SERIES_TOOLS
        + _TRAINING_PLAN_TOOLS
        + _SERVER_TOOLS
    )
    return [
        Tool(
            name=schema["name"],
            description=schema["description"],
            inputSchema=schema["inputSchema"],
        )
        for schema in all_schemas
    ]


# Tool name registry for validation
TOOL_NAMES: set[str] = {
    schema["name"]
    for group in [
        _EXPORT_TOOLS,
        _METADATA_TOOLS,
        _SPLITS_TOOLS,
        _ANALYSIS_TOOLS,
        _PHYSIOLOGY_TOOLS,
        _PERFORMANCE_TOOLS,
        _TIME_SERIES_TOOLS,
        _TRAINING_PLAN_TOOLS,
        _SERVER_TOOLS,
    ]
    for schema in group
}
