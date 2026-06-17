"""Time-series domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.

All four tools use ``input_schema_override`` because the original hand schemas
describe optional fields (``statistics_only``, ``z_threshold``, ...) *without*
emitting a JSON ``default`` key, and carry nested arrays / enums that the
standard normalization would not reproduce verbatim. The Pydantic models still
provide runtime defaults for dispatch.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

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

    activity_id: int
    split_number: int = Field(description="Split number (1-based)")
    metrics: list[str] | None = Field(
        default=None, description="List of metric names to extract (optional)"
    )
    statistics_only: bool | None = Field(
        default=None,
        description=(
            "If true, only return statistics (98.8% token reduction). Default: false"
        ),
    )
    detect_anomalies: bool | None = Field(
        default=None,
        description="Whether to detect anomalies in the data. Default: false",
    )
    z_threshold: float | None = Field(
        default=None,
        description="Z-score threshold for anomaly detection. Default: 2.0",
    )


class TimeRangeDetailParams(BaseModel):
    """Arguments for ``get_time_range_detail``."""

    activity_id: int
    start_time_s: int = Field(description="Start time in seconds")
    end_time_s: int = Field(description="End time in seconds")
    metrics: list[str] | None = Field(
        default=None, description="List of metric names to extract (optional)"
    )
    statistics_only: bool | None = Field(
        default=None,
        description=(
            "If true, only return statistics (mean, std, min, max) without time "
            "series data. Default: false"
        ),
    )


class DetectFormAnomaliesSummaryParams(BaseModel):
    """Arguments for ``detect_form_anomalies_summary``."""

    activity_id: int
    metrics: list[str] | None = Field(
        default=None, description="Metrics to analyze (default: GCT, VO, VR)"
    )
    z_threshold: float | None = Field(
        default=None,
        description="Z-score threshold for anomaly detection (default: 3.0)",
    )


class FormAnomalyDetailsParams(BaseModel):
    """Arguments for ``get_form_anomaly_details``."""

    activity_id: int
    anomaly_ids: list[int] | None = Field(
        default=None, description="Optional specific anomaly IDs to retrieve"
    )
    time_range: Annotated[list[int], Field(min_length=2, max_length=2)] | None = Field(
        default=None, description="Optional [start_sec, end_sec] time range"
    )
    metrics: list[str] | None = Field(
        default=None, description="Optional metric names to filter"
    )
    z_threshold: float | None = Field(
        default=None, description="Optional minimum z-score threshold"
    )
    causes: list[str] | None = Field(
        default=None,
        description="Optional causes to filter (elevation_change, pace_change, fatigue)",
    )
    limit: int = Field(
        default=50, description="Maximum number of results (default: 50)"
    )
    sort_by: Literal["z_score", "timestamp"] = Field(
        default="z_score", description="Sort order: z_score (desc) or timestamp (asc)"
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
    return detector.detect_form_anomalies_summary(
        activity_id=p.activity_id,
        metrics=p.metrics,
        z_threshold=p.z_threshold if p.z_threshold is not None else DEFAULT_Z_THRESHOLD,
    )


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
    filters["limit"] = p.limit

    return detector.get_form_anomaly_details(
        activity_id=p.activity_id,
        metrics=p.metrics,
        z_threshold=p.z_threshold if p.z_threshold is not None else DEFAULT_Z_THRESHOLD,
        filters=filters if filters else None,
    )


TIME_SERIES_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_split_time_series_detail",
        description=(
            "Get second-by-second detailed metrics for a specific 1km split "
            "(DuckDB-based, 98.8% token reduction)"
        ),
        params=SplitTimeSeriesDetailParams,
        handler=_get_split_time_series_detail,
        cli_group="time-series",
        cli_name="split-detail",
    ),
    ToolDef(
        name="get_time_range_detail",
        description="Get second-by-second detailed metrics for arbitrary time range",
        params=TimeRangeDetailParams,
        handler=_get_time_range_detail,
        cli_group="time-series",
        cli_name="time-range-detail",
    ),
    ToolDef(
        name="detect_form_anomalies_summary",
        description=(
            "Detect form anomalies and return lightweight summary (~700 tokens, "
            "95% reduction)"
        ),
        params=DetectFormAnomaliesSummaryParams,
        handler=_detect_form_anomalies_summary,
        cli_group="time-series",
        cli_name="anomalies-summary",
    ),
    ToolDef(
        name="get_form_anomaly_details",
        description=(
            "Get detailed anomaly information with flexible filtering (variable "
            "token size)"
        ),
        params=FormAnomalyDetailsParams,
        handler=_get_form_anomaly_details,
        cli_group="time-series",
        cli_name="anomaly-details",
    ),
]


TIME_SERIES_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in TIME_SERIES_TOOLS}
