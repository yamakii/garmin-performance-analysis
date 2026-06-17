"""Analysis domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.

The ``analyze_performance_trends`` and ``compare_similar_workouts`` schemas carry
nested array properties (``minItems``/``maxItems``) that the standard schema
normalization cannot reproduce, so they use ``input_schema_override``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class InsertSectionAnalysisParams(BaseModel):
    """Arguments for ``insert_section_analysis_dict``."""

    activity_id: int
    activity_date: str
    section_type: str
    analysis_data: dict[str, Any]


class ValidateSectionJsonParams(BaseModel):
    """Arguments for ``validate_section_json``."""

    section_type: str
    analysis_data: dict[str, Any]


class GetAnalysisContractParams(BaseModel):
    """Arguments for ``get_analysis_contract``."""

    section_type: str = Field(description="Section type")


class AnalyzePerformanceTrendsParams(BaseModel):
    """Arguments for ``analyze_performance_trends``."""

    metric: str
    start_date: str
    end_date: str
    activity_ids: list[int]
    activity_type: str | None = None
    temperature_range: list[float] | None = None
    distance_range: list[float] | None = None


class ExtractInsightsParams(BaseModel):
    """Arguments for ``extract_insights``."""

    keywords: list[str]
    activity_id: int | None = None
    section_types: list[str] | None = None
    limit: int = 10
    offset: int = 0
    max_tokens: int | None = None


class CompareSimilarWorkoutsParams(BaseModel):
    """Arguments for ``compare_similar_workouts``."""

    activity_id: int
    pace_tolerance: float | None = None
    distance_tolerance: float | None = None
    terrain_match: bool | None = None
    activity_type_filter: str | None = None
    date_range: list[str] | None = None
    limit: int | None = None


# ----------------------------------------------------------------------------
# Hand-written inputSchema overrides (nested arrays with minItems/maxItems and
# enums that the standard normalization cannot reproduce verbatim).
# ----------------------------------------------------------------------------

_VALIDATE_SECTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "section_type": {
            "type": "string",
            "enum": ["split", "phase", "efficiency", "environment", "summary"],
        },
        "analysis_data": {"type": "object"},
    },
    "required": ["section_type", "analysis_data"],
}

_GET_ANALYSIS_CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "section_type": {
            "type": "string",
            "description": "Section type",
            "enum": ["split", "phase", "efficiency", "environment", "summary"],
        },
    },
    "required": ["section_type"],
}

_ANALYZE_PERFORMANCE_TRENDS_SCHEMA: dict[str, Any] = {
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
}

_EXTRACT_INSIGHTS_SCHEMA: dict[str, Any] = {
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
}

_COMPARE_SIMILAR_WORKOUTS_SCHEMA: dict[str, Any] = {
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
}


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _insert_section_analysis_dict(
    reader: GarminDBReader, p: InsertSectionAnalysisParams
) -> dict[str, Any]:
    from garmin_mcp.database.inserters.section_analyses import insert_section_analysis

    success = insert_section_analysis(
        activity_id=p.activity_id,
        activity_date=p.activity_date,
        section_type=p.section_type,
        analysis_data=p.analysis_data,
    )
    return {
        "success": success,
        "activity_id": p.activity_id,
        "section_type": p.section_type,
    }


def _validate_section_json(
    reader: GarminDBReader, p: ValidateSectionJsonParams
) -> dict[str, Any]:
    from garmin_mcp.validation.section_schemas import validate_section_data

    valid, errors = validate_section_data(p.section_type, p.analysis_data)
    return {
        "valid": valid,
        "errors": errors,
        "section_type": p.section_type,
    }


def _get_analysis_contract(
    reader: GarminDBReader, p: GetAnalysisContractParams
) -> dict[str, Any]:
    from garmin_mcp.validation.contracts import get_contract

    try:
        return get_contract(p.section_type)
    except ValueError as e:
        return {"error": str(e)}


def _analyze_performance_trends(
    reader: GarminDBReader, p: AnalyzePerformanceTrendsParams
) -> Any:
    from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer

    trend_analyzer = PerformanceTrendAnalyzer()

    temperature_range: tuple[float, float] | None = (
        (p.temperature_range[0], p.temperature_range[1])
        if p.temperature_range is not None
        else None
    )
    distance_range: tuple[float, float] | None = (
        (p.distance_range[0], p.distance_range[1])
        if p.distance_range is not None
        else None
    )

    return trend_analyzer.analyze_metric_trend(
        metric=p.metric,
        start_date=p.start_date,
        end_date=p.end_date,
        activity_ids=p.activity_ids,
        activity_type=p.activity_type,
        temperature_range=temperature_range,
        distance_range=distance_range,
    )


def _extract_insights(reader: GarminDBReader, p: ExtractInsightsParams) -> Any:
    from garmin_mcp.rag.queries.insights import InsightExtractor

    insight_extractor = InsightExtractor()

    if p.activity_id is not None:
        return insight_extractor.extract_insights(
            activity_id=p.activity_id,
            keywords=p.keywords,
            max_tokens=p.max_tokens,
        )
    return insight_extractor.search_by_keywords(
        keywords=p.keywords,
        section_types=p.section_types,
        limit=p.limit,
        offset=p.offset,
    )


def _compare_similar_workouts(
    reader: GarminDBReader, p: CompareSimilarWorkoutsParams
) -> Any:
    from garmin_mcp.rag.queries.comparisons import WorkoutComparator

    comparator = WorkoutComparator()
    date_range: tuple[str, str] | None = (
        (p.date_range[0], p.date_range[1]) if p.date_range else None
    )

    return comparator.find_similar_workouts(
        activity_id=p.activity_id,
        pace_tolerance=p.pace_tolerance if p.pace_tolerance is not None else 0.2,
        distance_tolerance=(
            p.distance_tolerance if p.distance_tolerance is not None else 0.2
        ),
        terrain_match=p.terrain_match if p.terrain_match is not None else False,
        activity_type_filter=p.activity_type_filter,
        date_range=date_range,
        limit=p.limit if p.limit is not None else 10,
    )


ANALYSIS_TOOLS: list[ToolDef] = [
    ToolDef(
        name="insert_section_analysis_dict",
        description="Insert section analysis dict directly into DuckDB (no file creation)",
        params=InsertSectionAnalysisParams,
        handler=_insert_section_analysis_dict,
        cli_group="analysis",
        cli_name="insert-section",
    ),
    ToolDef(
        name="validate_section_json",
        description=(
            "Validate section analysis data against Pydantic schema. Returns "
            "{valid: bool, errors: list[str]}."
        ),
        params=ValidateSectionJsonParams,
        handler=_validate_section_json,
        cli_group="analysis",
        cli_name="validate-section",
        input_schema_override=_VALIDATE_SECTION_JSON_SCHEMA,
    ),
    ToolDef(
        name="get_analysis_contract",
        description=(
            "Get analysis contract for a section type (output schema, evaluation "
            "thresholds, instructions). Agents call this for up-to-date evaluation "
            "criteria."
        ),
        params=GetAnalysisContractParams,
        handler=_get_analysis_contract,
        cli_group="analysis",
        cli_name="contract",
        input_schema_override=_GET_ANALYSIS_CONTRACT_SCHEMA,
    ),
    ToolDef(
        name="analyze_performance_trends",
        description="Analyze performance trends across multiple activities with filtering (Phase 3.1)",
        params=AnalyzePerformanceTrendsParams,
        handler=_analyze_performance_trends,
        cli_group="analysis",
        cli_name="performance-trends",
        input_schema_override=_ANALYZE_PERFORMANCE_TRENDS_SCHEMA,
    ),
    ToolDef(
        name="extract_insights",
        description="Extract insights from section analyses using keyword-based search (Phase 3.2)",
        params=ExtractInsightsParams,
        handler=_extract_insights,
        cli_group="analysis",
        cli_name="extract-insights",
        input_schema_override=_EXTRACT_INSIGHTS_SCHEMA,
    ),
    ToolDef(
        name="compare_similar_workouts",
        description="Find and compare similar past workouts based on pace and distance (Phase 4.5)",
        params=CompareSimilarWorkoutsParams,
        handler=_compare_similar_workouts,
        cli_group="analysis",
        cli_name="compare-workouts",
        input_schema_override=_COMPARE_SIMILAR_WORKOUTS_SCHEMA,
    ),
]


ANALYSIS_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ANALYSIS_TOOLS}
