"""Splits domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.

``get_interval_analysis`` lives in the splits schema group (and CLI group) even
though it is delegated to a dedicated analyzer rather than a direct reader call.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef


class SplitsStatsParams(BaseModel):
    """Shared ``activity_id`` + ``statistics_only`` args for the split readers."""

    activity_id: int
    statistics_only: bool = False


class IntervalAnalysisParams(BaseModel):
    """Arguments for ``get_interval_analysis``."""

    activity_id: int


def _inject_split_warnings(result: Any) -> Any:
    """Attach a ``_warnings`` field when splits are missing form metrics."""
    splits = result.get("splits") if isinstance(result, dict) else None
    if splits:
        missing_form = sum(1 for s in splits if s.get("ground_contact_time_ms") is None)
        if missing_form > 0 and isinstance(result, dict):
            result["_warnings"] = [
                f"{missing_form}/{len(splits)} splits missing form metrics"
            ]
    return result


def _get_splits_pace_hr(reader: GarminDBReader, p: SplitsStatsParams) -> Any:
    result = reader.get_splits_pace_hr(p.activity_id, statistics_only=p.statistics_only)
    return _inject_split_warnings(result)


def _get_splits_form_metrics(reader: GarminDBReader, p: SplitsStatsParams) -> Any:
    result = reader.get_splits_form_metrics(
        p.activity_id, statistics_only=p.statistics_only
    )
    return _inject_split_warnings(result)


def _get_splits_elevation(reader: GarminDBReader, p: SplitsStatsParams) -> Any:
    result = reader.get_splits_elevation(
        p.activity_id, statistics_only=p.statistics_only
    )
    return _inject_split_warnings(result)


def _get_splits_comprehensive(reader: GarminDBReader, p: SplitsStatsParams) -> Any:
    result = reader.get_splits_comprehensive(
        p.activity_id, statistics_only=p.statistics_only
    )
    return _inject_split_warnings(result)


def _get_interval_analysis(reader: GarminDBReader, p: IntervalAnalysisParams) -> Any:
    from garmin_mcp.rag.queries.interval_analysis import IntervalAnalyzer

    analyzer = IntervalAnalyzer()
    return analyzer.get_interval_analysis(activity_id=p.activity_id)


SPLITS_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_splits_pace_hr",
        description=(
            "Deprecated: use get_splits_comprehensive instead. Get pace and heart "
            "rate data from splits (lightweight: ~3 fields/split, or ~200 bytes "
            "with statistics_only=True)"
        ),
        params=SplitsStatsParams,
        handler=_get_splits_pace_hr,
        cli_group="splits",
        cli_name="pace-hr",
        field_descriptions={
            "statistics_only": (
                "If true, return only aggregated statistics (mean, median, std, "
                "min, max) instead of per-split data. Reduces output size by ~80%. "
                "Default: false"
            )
        },
    ),
    ToolDef(
        name="get_splits_form_metrics",
        description=(
            "Deprecated: use get_splits_comprehensive instead. Get form efficiency "
            "metrics from splits (lightweight: ~4 fields/split, or ~300 bytes with "
            "statistics_only=True)"
        ),
        params=SplitsStatsParams,
        handler=_get_splits_form_metrics,
        cli_group="splits",
        cli_name="form-metrics",
        field_descriptions={
            "statistics_only": (
                "If true, return only aggregated statistics (mean, median, std, "
                "min, max) for GCT, VO, VR instead of per-split data. Reduces "
                "output size by ~80%. Default: false"
            )
        },
    ),
    ToolDef(
        name="get_splits_elevation",
        description=(
            "Get elevation and terrain data from splits (lightweight: ~5 "
            "fields/split, or ~250 bytes with statistics_only=True)"
        ),
        params=SplitsStatsParams,
        handler=_get_splits_elevation,
        cli_group="splits",
        cli_name="elevation",
        field_descriptions={
            "statistics_only": (
                "If true, return only aggregated statistics (mean, median, std, "
                "min, max) for elevation gain/loss instead of per-split data. "
                "Reduces output size by ~80%. Default: false"
            )
        },
    ),
    ToolDef(
        name="get_splits_comprehensive",
        description=(
            "Get comprehensive split data (12 fields: pace, HR, form, power, "
            "cadence, elevation). Supports statistics_only mode for 67% token "
            "reduction."
        ),
        params=SplitsStatsParams,
        handler=_get_splits_comprehensive,
        cli_group="splits",
        cli_name="comprehensive",
        field_descriptions={
            "statistics_only": (
                "If true, return only aggregated statistics (mean, median, std, "
                "min, max) instead of per-split data. Reduces output size by ~67%. "
                "Default: false"
            )
        },
    ),
    ToolDef(
        name="get_interval_analysis",
        description=(
            "Analyze interval training Work/Recovery segments using intensity_type "
            "from DuckDB"
        ),
        params=IntervalAnalysisParams,
        handler=_get_interval_analysis,
        cli_group="splits",
        cli_name="interval-analysis",
    ),
]


SPLITS_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in SPLITS_TOOLS}
