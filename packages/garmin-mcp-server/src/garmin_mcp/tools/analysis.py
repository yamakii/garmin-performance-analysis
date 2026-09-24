"""Analysis domain tool definitions.

The ``analyze_performance_trends`` and ``compare_similar_workouts`` schemas carry
nested array properties (``minItems``/``maxItems``) that the standard schema
normalization cannot reproduce, so they use ``input_schema_override``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ACTIVITY_ID_DESCRIPTION, ToolDef

_SECTION_TYPES = Literal["run_note"]

# ----------------------------------------------------------------------------
# Params models
# ----------------------------------------------------------------------------


class InsertSectionAnalysisParams(BaseModel):
    """Arguments for ``insert_section_analysis_dict``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    activity_date: str = Field(description="Activity date, YYYY-MM-DD")
    section_type: str = Field(description="Section type of the row, e.g. run_note")
    analysis_data: dict[str, Any] = Field(
        description="The section's analysis_data object, stored as given"
    )


class ValidateSectionJsonParams(BaseModel):
    """Arguments for ``validate_section_json``."""

    section_type: _SECTION_TYPES = Field(description="Section type to validate")
    analysis_data: dict[str, Any] = Field(
        description="The analysis_data object to check against the section schema"
    )


class GetAnalysisContractParams(BaseModel):
    """Arguments for ``get_analysis_contract``."""

    section_type: _SECTION_TYPES = Field(description="Section type")


class FindUnanalyzedActivitiesParams(BaseModel):
    """Arguments for ``find_unanalyzed_activities``."""

    start_date: str = Field(description="Start date (inclusive) in YYYY-MM-DD format")
    end_date: str = Field(description="End date (inclusive) in YYYY-MM-DD format")
    required_sections: int = Field(
        default=5,
        description="Legacy section count considered complete (default 5)",
    )


class AnalyzePerformanceTrendsParams(BaseModel):
    """Arguments for ``analyze_performance_trends``."""

    metric: str = Field(
        description=(
            "pace (s/km), heart_rate, cadence, power, vertical_oscillation, "
            "ground_contact_time, vertical_ratio or elevation_gain (mean per-lap "
            "gain); distance and training_effect are accepted but always return "
            "insufficient_data"
        )
    )
    start_date: str = Field(
        description="Echoed in the result only; does not filter (choose activity_ids)"
    )
    end_date: str = Field(
        description="Echoed in the result only; does not filter (choose activity_ids)"
    )
    activity_ids: list[int] = Field(
        description="Activities to include; this list alone defines the sample"
    )
    activity_type: str | None = Field(
        default=None, description="Not supported; any value raises an error"
    )
    temperature_range: (
        Annotated[list[float], Field(min_length=2, max_length=2)] | None
    ) = Field(
        default=None,
        description=(
            "Keep only activities whose weather-station temperature (°C) is within "
            "[min, max]; runs without weather are dropped"
        ),
    )
    distance_range: Annotated[list[float], Field(min_length=2, max_length=2)] | None = (
        Field(
            default=None,
            description="Keep only activities whose total distance (km) is within [min, max]",
        )
    )


class GetHeatAdjustedTrendParams(BaseModel):
    """Arguments for ``get_heat_adjusted_trend``."""

    start_date: str = Field(
        description="Inclusive start (YYYY-MM-DD); runs dated earlier are dropped"
    )
    end_date: str = Field(
        description="Inclusive end (YYYY-MM-DD); runs dated later are dropped"
    )
    activity_ids: list[int] = Field(
        description=(
            "Activities to fit on; only those dated in the window with HR, pace "
            "and temperature are used"
        )
    )
    ref_temp_c: float | None = Field(
        default=None,
        description="Hinge reference temperature in Celsius (default 15)",
    )


class ExtractInsightsParams(BaseModel):
    """Arguments for ``extract_insights``.

    NOTE: ``activity_id`` is a deliberately *internal* validation field used by
    the handler but intentionally absent from the documented MCP surface (the
    original hand schema never exposed it). Deriving the schema would surface
    ``activity_id`` and break byte-parity, so this tool keeps an
    ``input_schema_override`` (the one remaining override).
    """

    keywords: list[str]
    activity_id: int | None = None
    section_types: list[str] | None = None
    limit: int = 10
    offset: int = 0
    max_tokens: int | None = None


class CompareSimilarWorkoutsParams(BaseModel):
    """Arguments for ``compare_similar_workouts``."""

    activity_id: int = Field(
        description=(
            "Garmin activity ID of the target run (resolve one from a date with "
            "get_activity_by_date)"
        )
    )
    pace_tolerance: float | None = Field(
        default=None,
        description=(
            "Allowed fractional difference from the target's average pace in s/km "
            "(default 0.2 = ±20%)"
        ),
    )
    distance_tolerance: float | None = Field(
        default=None,
        description="Distance tolerance as fraction (default 0.2 = ±20%)",
    )
    terrain_match: bool | None = Field(
        default=None, description="Accepted but currently ignored"
    )
    activity_type_filter: str | None = Field(
        default=None,
        description="Substring matched against activity_name (SQL LIKE), not a workout type",
    )
    date_range: list[str] | None = Field(
        default=None,
        description="Optional [start, end] (YYYY-MM-DD, inclusive) limiting candidates",
    )
    limit: int | None = Field(
        default=None, description="Maximum number of results (default 10)"
    )


# ----------------------------------------------------------------------------
# Remaining hand-written inputSchema override.
#
# Only ``extract_insights`` keeps an override: its params model carries an
# internal ``activity_id`` validation field that the documented MCP surface
# intentionally hides, so a derived schema would not be byte-identical.
# ----------------------------------------------------------------------------

_EXTRACT_INSIGHTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Top-level analysis_data field names; a row matches when any is "
                "non-empty. run_note: story, good_points, growth_points, "
                "next_challenge, next_challenge_evidence, timeline, notes, question. "
                "key_strengths / improvement_areas / efficiency / evaluation / "
                "environmental_impact exist only on legacy rows"
            ),
        },
        "section_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Restrict to these section types (run_note, or legacy "
                "efficiency/environment/phase/split/summary)"
            ),
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
            "description": "Ignored by this tool; page with limit/offset",
        },
    },
    "required": ["keywords"],
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


def _find_unanalyzed_activities(
    reader: GarminDBReader, p: FindUnanalyzedActivitiesParams
) -> Any:
    return reader.find_unanalyzed_activities(
        start_date=p.start_date,
        end_date=p.end_date,
        required_sections=p.required_sections,
    )


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


def _get_heat_adjusted_trend(
    reader: GarminDBReader, p: GetHeatAdjustedTrendParams
) -> Any:
    return reader.get_heat_adjusted_trend(
        activity_ids=p.activity_ids,
        start_date=p.start_date,
        end_date=p.end_date,
        ref_temp_c=p.ref_temp_c if p.ref_temp_c is not None else 15.0,
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
        description=(
            "Append one section_analyses row (activity_id, activity_date, "
            "section_type, analysis_data) verbatim to DuckDB as a new version "
            "(fresh run_id); readers treat the latest version as canonical and "
            "prior versions are kept. Does NOT run the run_note schema or "
            "grounding gate - the normal path is validate_section_json then "
            "merge_section_analyses via the analyze-activity workflow. Use only "
            "for manual repair."
        ),
        params=InsertSectionAnalysisParams,
        handler=_insert_section_analysis_dict,
        cli_group="analysis",
        cli_name="insert-section",
    ),
    ToolDef(
        name="validate_section_json",
        description=(
            "Validate a run_note coach review against its Pydantic schema. "
            "Returns {valid: bool, errors: list[str]}."
        ),
        params=ValidateSectionJsonParams,
        handler=_validate_section_json,
        cli_group="analysis",
        cli_name="validate-section",
    ),
    ToolDef(
        name="get_analysis_contract",
        description=(
            "Get the analysis contract for the run_note coach review (output "
            "schema, evidence keys, writing criterion). The analyst calls this "
            "for the up-to-date criterion."
        ),
        params=GetAnalysisContractParams,
        handler=_get_analysis_contract,
        cli_group="analysis",
        cli_name="contract",
    ),
    ToolDef(
        name="find_unanalyzed_activities",
        description=(
            "Find running activities without an analysis in a date range. An "
            "activity counts as analysed when it has a run_note row or the "
            "complete legacy section set. Returns [{activity_id, date, "
            "section_count}] for the rest, where section_count is the distinct "
            "legacy section count, ordered by date ascending. Used to backfill "
            "analysis history for catch-up-ingested days."
        ),
        params=FindUnanalyzedActivitiesParams,
        handler=_find_unanalyzed_activities,
        cli_group="analysis",
        cli_name="find-unanalyzed",
    ),
    ToolDef(
        name="analyze_performance_trends",
        description=(
            "Linear trend of one metric across the given activity_ids: each "
            "activity contributes the unweighted mean of the metric over its "
            "laps, regressed on elapsed days. Returns metric, trend (stable when "
            "p>0.05, insufficient_data under 3 points), slope (metric units per "
            "day), correlation, p_value, data_points, start_date, end_date. Only "
            "pace treats a falling value as improving; for every other metric a "
            "rising value is labelled improving, so read the slope sign."
        ),
        params=AnalyzePerformanceTrendsParams,
        handler=_analyze_performance_trends,
        cli_group="analysis",
        cli_name="performance-trends",
    ),
    ToolDef(
        name="get_heat_adjusted_trend",
        description=(
            "Climate-neutral HR-at-pace trend: fits HR ~ pace + max(temp - "
            "ref_temp_c, 0) + days on whole-run averages (HR, pace, "
            "weather-station temperature) of the activity_ids dated within "
            "start_date..end_date. Returns status, coefficients (beta_heat = bpm "
            "per °C above ref, n, r_squared), neutral_hr_slope (bpm/day) with its "
            "p_value, and points[] {date, temp_c, raw_hr, heat_cost, neutral_hr}. "
            "Needs 10 complete runs, else status=insufficient_data. Workout types "
            "are mixed."
        ),
        params=GetHeatAdjustedTrendParams,
        handler=_get_heat_adjusted_trend,
        cli_group="analysis",
        cli_name="heat-adjusted-trend",
    ),
    ToolDef(
        name="extract_insights",
        description=(
            "List stored section_analyses rows whose analysis_data has a non-empty "
            "top-level field named in keywords (a field-name match, not a text "
            "search). Returns a list of {activity_id, activity_date, section_type, "
            "analysis_data} with the whole JSON, newest first, paged by "
            "limit/offset; every stored version is returned, not just the latest. "
            "run_note fields are story, good_points, growth_points, "
            "next_challenge, timeline, notes, question."
        ),
        params=ExtractInsightsParams,
        handler=_extract_insights,
        cli_group="analysis",
        cli_name="extract-insights",
        input_schema_override=_EXTRACT_INSIGHTS_SCHEMA,
    ),
    ToolDef(
        name="compare_similar_workouts",
        description=(
            "Find other activities whose whole-run average pace and total distance "
            "are within tolerance of the target, ordered by pace closeness then "
            "recency. Returns target_activity and similar_activities[] with "
            "training_type, temperature and its diff, similarity_score (0-100: "
            "pace 45%, distance 35%, training type 20%), pace_diff (s/km) and "
            "hr_diff (bpm) as candidate minus target, and a Japanese "
            "interpretation. Candidates may be dated after the target."
        ),
        params=CompareSimilarWorkoutsParams,
        handler=_compare_similar_workouts,
        cli_group="analysis",
        cli_name="compare-workouts",
    ),
]


ANALYSIS_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ANALYSIS_TOOLS}
