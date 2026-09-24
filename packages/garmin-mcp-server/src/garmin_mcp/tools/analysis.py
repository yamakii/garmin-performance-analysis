"""Analysis domain tool definitions."""

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
            "gain); any other value returns an error listing these"
        )
    )
    start_date: str = Field(
        description="Inclusive start (YYYY-MM-DD); activities dated earlier are dropped"
    )
    end_date: str = Field(
        description="Inclusive end (YYYY-MM-DD); activities dated later are dropped"
    )
    activity_ids: list[int] | None = Field(
        default=None,
        description=(
            "Activities to consider; only those dated in the window are used. "
            "Omit to use every run dated in the window"
        ),
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

    try:
        return trend_analyzer.analyze_metric_trend(
            metric=p.metric,
            start_date=p.start_date,
            end_date=p.end_date,
            activity_ids=p.activity_ids,
            temperature_range=temperature_range,
            distance_range=distance_range,
        )
    except ValueError as e:
        return {"error": str(e)}


def _get_heat_adjusted_trend(
    reader: GarminDBReader, p: GetHeatAdjustedTrendParams
) -> Any:
    return reader.get_heat_adjusted_trend(
        activity_ids=p.activity_ids,
        start_date=p.start_date,
        end_date=p.end_date,
        ref_temp_c=p.ref_temp_c if p.ref_temp_c is not None else 15.0,
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
            "Returns {valid: bool, errors: list[str]}. Only section_type "
            "run_note is accepted. This checks the schema only: the grounding "
            "gate (every evidence key must resolve against the run report) runs "
            "at merge, so valid: true does not mean the merge will accept it."
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
            "Linear trend of one metric across the activity_ids dated within "
            "start_date..end_date (omit activity_ids to use every run in the "
            "window): each activity contributes the unweighted mean "
            "of the metric over its laps, regressed on elapsed days. Returns "
            "metric, trend, slope (metric units per day), correlation, p_value, "
            "data_points, start_date, end_date. trend is stable when p>0.05 and "
            "insufficient_data under 3 points. Otherwise pace, "
            "ground_contact_time, vertical_oscillation and vertical_ratio "
            "(lower is better) read improving / declining, while heart_rate, "
            "power, cadence and elevation_gain, which are not comparable across "
            "runs at different paces, read only increasing / decreasing."
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
        name="compare_similar_workouts",
        description=(
            "Find earlier activities whose whole-run average pace and total "
            "distance are within tolerance of the target, ordered by pace "
            "closeness then recency. Only runs that started before the target "
            "are candidates (an earlier date, or the same date with an earlier "
            "start), so an old run is never compared with later ones. Returns "
            "target_activity and similar_activities[] with training_type, "
            "temperature and its diff, similarity_score (0-100: pace 45%, "
            "distance 35%, training type 20%), pace_diff (s/km) and hr_diff (bpm) "
            "as candidate minus target, and a Japanese interpretation."
        ),
        params=CompareSimilarWorkoutsParams,
        handler=_compare_similar_workouts,
        cli_group="analysis",
        cli_name="compare-workouts",
    ),
]


ANALYSIS_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in ANALYSIS_TOOLS}
