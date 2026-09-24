"""Time-series domain tool definitions.

Optional fields (``statistics_only``, ``z_threshold``, ...) are modeled as
``... | None = None`` so the derived schema emits no JSON ``default`` key; the
handlers coalesce them to their runtime defaults.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ACTIVITY_ID_DESCRIPTION, ToolDef

_METRICS_DESCRIPTION = (
    "time_series_metrics column names, e.g. heart_rate, speed (m/s), cadence "
    "(spm, both feet), power, ground_contact_time, vertical_oscillation, "
    "vertical_ratio, stride_length, elevation, grade_adjusted_speed, "
    "air_temperature (device sensor); default: heart_rate, speed, cadence, "
    "power, vertical_oscillation, ground_contact_time, vertical_ratio. Unknown "
    "names return an error"
)

_FORM_DESCRIPTOR_METRICS = (
    "Garmin descriptor keys directGroundContactTime, directVerticalOscillation, "
    "directVerticalRatio (the default) or the short names GCT / VO / VR, "
    "case-insensitive. Unknown names return an error"
)

# ----------------------------------------------------------------------------
# Params models (drive validation, the CLI signature, and the derived MCP
# schema). Optional fields whose hand schema emitted no ``default`` key are
# modeled as ``... | None = None`` and coalesced to their runtime default in the
# handler, so behavior is unchanged while the schema stays byte-identical.
# ----------------------------------------------------------------------------

# Runtime defaults preserved from the previous Pydantic models.
_DEFAULT_STATISTICS_ONLY = False
_DEFAULT_DETECT_ANOMALIES = False
_DEFAULT_SPLIT_Z_THRESHOLD = 2.0


class SplitTimeSeriesDetailParams(BaseModel):
    """Arguments for ``get_split_time_series_detail``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    split_number: int = Field(
        description="Lap number (1-based), as split_number in get_splits_comprehensive"
    )
    metrics: list[str] | None = Field(default=None, description=_METRICS_DESCRIPTION)
    statistics_only: bool | None = Field(
        default=None,
        description=(
            "If true, return only statistics {mean, std, min, max} per metric, "
            "without time_series. Default: false"
        ),
    )
    detect_anomalies: bool | None = Field(
        default=None,
        description=(
            "If true, add anomalies[] for this lap (z versus the whole-activity "
            "mean/std). Default: false"
        ),
    )
    z_threshold: float | None = Field(
        default=None,
        description="Absolute z above which a sample is an anomaly. Default: 2.0",
    )


class TimeRangeDetailParams(BaseModel):
    """Arguments for ``get_time_range_detail``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    start_time_s: int = Field(
        description="Inclusive start, seconds elapsed since the activity start"
    )
    end_time_s: int = Field(
        description="Exclusive end, seconds elapsed since the activity start"
    )
    metrics: list[str] | None = Field(default=None, description=_METRICS_DESCRIPTION)
    statistics_only: bool | None = Field(
        default=None,
        description=(
            "If true, only return statistics (mean, std, min, max) without time "
            "series data. Default: false"
        ),
    )


class DetectFormAnomaliesSummaryParams(BaseModel):
    """Arguments for ``detect_form_anomalies_summary``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    metrics: list[str] | None = Field(
        default=None, description=_FORM_DESCRIPTOR_METRICS
    )
    z_threshold: float | None = Field(
        default=None,
        description="Minimum z versus the rolling baseline (default: 3.0)",
    )


class FormAnomalyDetailsParams(BaseModel):
    """Arguments for ``get_form_anomaly_details``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    anomaly_ids: list[int] | None = Field(
        default=None,
        description=(
            "anomaly_id values from an earlier call with the same metrics and "
            "z_threshold"
        ),
    )
    time_range: Annotated[list[int], Field(min_length=2, max_length=2)] | None = Field(
        default=None, description="[start, end] elapsed seconds, inclusive"
    )
    metrics: list[str] | None = Field(
        default=None,
        description=(
            "Form metrics to detect and return: descriptor keys "
            "directGroundContactTime, directVerticalOscillation, "
            "directVerticalRatio (the default) or GCT / VO / VR, "
            "case-insensitive. Unknown names return an error"
        ),
    )
    z_threshold: float | None = Field(
        default=None,
        description="Detection threshold and minimum |z| filter (default: 3.0)",
    )
    causes: list[str] | None = Field(
        default=None,
        description="Keep only these: elevation_change, pace_change, fatigue, isolated",
    )
    limit: int = Field(
        default=50, description="Maximum number of results (default: 50)"
    )
    sort_by: Literal["z_score", "timestamp"] = Field(
        default="z_score",
        description=(
            "z_score = |z_score| descending (default), timestamp = ascending; "
            "applied before limit"
        ),
    )


# ----------------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------------


def _get_split_time_series_detail(
    reader: GarminDBReader, p: SplitTimeSeriesDetailParams
) -> Any:
    from garmin_mcp.rag.queries.time_series_detail import TimeSeriesDetailExtractor

    extractor = TimeSeriesDetailExtractor()
    return extractor.get_split_time_series_detail(
        activity_id=p.activity_id,
        split_number=p.split_number,
        metrics=p.metrics,
        statistics_only=(
            p.statistics_only
            if p.statistics_only is not None
            else _DEFAULT_STATISTICS_ONLY
        ),
        detect_anomalies=(
            p.detect_anomalies
            if p.detect_anomalies is not None
            else _DEFAULT_DETECT_ANOMALIES
        ),
        z_threshold=(
            p.z_threshold if p.z_threshold is not None else _DEFAULT_SPLIT_Z_THRESHOLD
        ),
    )


def _get_time_range_detail(reader: GarminDBReader, p: TimeRangeDetailParams) -> Any:
    from garmin_mcp.rag.queries.time_series_detail import TimeSeriesDetailExtractor

    extractor = TimeSeriesDetailExtractor()
    return extractor.extract_metrics(
        activity_id=p.activity_id,
        start_time=p.start_time_s,
        end_time=p.end_time_s,
        metrics=p.metrics,
        statistics_only=(
            p.statistics_only
            if p.statistics_only is not None
            else _DEFAULT_STATISTICS_ONLY
        ),
    )


def _detect_form_anomalies_summary(
    reader: GarminDBReader, p: DetectFormAnomaliesSummaryParams
) -> Any:
    from garmin_mcp.rag.queries.form_anomaly_detector import (
        DEFAULT_Z_THRESHOLD,
        FormAnomalyDetector,
    )

    detector = FormAnomalyDetector()
    try:
        return detector.detect_form_anomalies_summary(
            activity_id=p.activity_id,
            metrics=p.metrics,
            z_threshold=(
                p.z_threshold if p.z_threshold is not None else DEFAULT_Z_THRESHOLD
            ),
        )
    except ValueError as e:
        return {"error": str(e)}


def _get_form_anomaly_details(
    reader: GarminDBReader, p: FormAnomalyDetailsParams
) -> Any:
    from garmin_mcp.rag.queries.form_anomaly_detector import (
        DEFAULT_Z_THRESHOLD,
        FormAnomalyDetector,
    )

    detector = FormAnomalyDetector()

    filters: dict[str, Any] = {}
    if p.anomaly_ids is not None:
        filters["anomaly_ids"] = p.anomaly_ids
    if p.time_range is not None:
        filters["time_range"] = tuple(p.time_range)
    if p.metrics is not None:
        filters["metrics"] = p.metrics
    if p.z_threshold is not None:
        filters["min_z_score"] = p.z_threshold
    if p.causes is not None:
        filters["causes"] = p.causes
    filters["sort_by"] = p.sort_by
    filters["limit"] = p.limit

    try:
        return detector.get_form_anomaly_details(
            activity_id=p.activity_id,
            metrics=p.metrics,
            z_threshold=(
                p.z_threshold if p.z_threshold is not None else DEFAULT_Z_THRESHOLD
            ),
            filters=filters,
        )
    except ValueError as e:
        return {"error": str(e)}


TIME_SERIES_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_split_time_series_detail",
        description=(
            "Sample-level data for one lap (split_number as in "
            "get_splits_comprehensive; laps are auto 1 km or workout/manual laps) "
            "from time_series_metrics. Returns time_range, metrics, statistics "
            "{mean, std, min, max} and, unless statistics_only, time_series. With "
            "detect_anomalies, anomalies[] {timestamp_s, metric, value, z_score} "
            "lists samples in this lap whose absolute z against the "
            "whole-activity mean and std exceeds z_threshold, in either direction."
        ),
        params=SplitTimeSeriesDetailParams,
        handler=_get_split_time_series_detail,
        cli_group="time-series",
        cli_name="split-detail",
    ),
    ToolDef(
        name="get_time_range_detail",
        description=(
            "Recorded samples of chosen metrics for one activity between "
            "start_time_s and end_time_s (elapsed seconds, end exclusive), from "
            "time_series_metrics. Returns time_range, metrics, statistics {mean, "
            "std, min, max} per metric and, unless statistics_only, time_series "
            "[{timestamp_s, metric: value}]. Long runs are recorded about every "
            "2 s, so rows are not per second. A metric with no data reads 0.0 in "
            "statistics."
        ),
        params=TimeRangeDetailParams,
        handler=_get_time_range_detail,
        cli_group="time-series",
        cli_name="time-range-detail",
    ),
    ToolDef(
        name="detect_form_anomalies_summary",
        description=(
            "Scan one activity's raw activity_details samples for sustained form "
            "deterioration: a sample counts when its z against a rolling "
            "60-sample baseline exceeds z_threshold in the worse (higher) "
            "direction, passes a magnitude gate (GCT 10 ms, VO 0.5 cm, VR 0.3 %) "
            "and lasts 5 s. Returns anomalies_detected, counts per metric and per "
            "cause (elevation_change/pace_change/fatigue/isolated), severity "
            "bands, 5-minute clusters, the top 5 and Japanese recommendations."
        ),
        params=DetectFormAnomaliesSummaryParams,
        handler=_detect_form_anomalies_summary,
        cli_group="time-series",
        cli_name="anomalies-summary",
    ),
    ToolDef(
        name="get_form_anomaly_details",
        description=(
            "Full records for the anomalies detect_form_anomalies_summary counts, "
            "after filters. Each has anomaly_id, timestamp (elapsed s), metric, "
            "value, baseline (rolling mean), z_score, probable_cause "
            "(elevation_change/pace_change/fatigue/isolated), cause_details and "
            "30 s before/after context. Returns total_anomalies, "
            "returned_anomalies and anomalies ordered by sort_by (absolute "
            "z_score descending, or timestamp ascending), capped by limit."
        ),
        params=FormAnomalyDetailsParams,
        handler=_get_form_anomaly_details,
        cli_group="time-series",
        cli_name="anomaly-details",
    ),
]


TIME_SERIES_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in TIME_SERIES_TOOLS}
