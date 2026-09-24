"""Splits domain tool definitions.

``get_interval_analysis`` lives in the splits schema group (and CLI group) even
though it is delegated to a dedicated analyzer rather than a direct reader call.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ACTIVITY_ID_DESCRIPTION, ToolDef


class SplitsStatsParams(BaseModel):
    """Shared ``activity_id`` + ``statistics_only`` args for the split readers."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)
    statistics_only: bool = False


class IntervalAnalysisParams(BaseModel):
    """Arguments for ``get_interval_analysis``."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)


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


def _get_splits_elevation(reader: GarminDBReader, p: SplitsStatsParams) -> Any:
    # No form-metric warning: elevation rows never carry form metrics.
    return reader.get_splits_elevation(p.activity_id, statistics_only=p.statistics_only)


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
        name="get_splits_elevation",
        description=(
            "Per-lap elevation for one activity from the splits table (Garmin "
            "laps: auto 1 km, or workout/manual laps). Full mode returns splits[] "
            "with split_number, elevation_gain_m, elevation_loss_m and "
            "terrain_type (平坦/起伏/丘陵/山岳). statistics_only returns "
            "metrics.elevation_gain / elevation_loss as {mean, median, std, min, "
            "max} in metres, without terrain_type. get_splits_comprehensive "
            "carries the same gain/loss; this tool adds the terrain class."
        ),
        params=SplitsStatsParams,
        handler=_get_splits_elevation,
        cli_group="splits",
        cli_name="elevation",
        field_descriptions={
            "statistics_only": (
                "If true, return only aggregated statistics (mean, median, std, "
                "min, max) for elevation gain/loss instead of per-split data. "
                "Default: false"
            )
        },
    ),
    ToolDef(
        name="get_splits_comprehensive",
        description=(
            "Per-lap data for one activity from the splits table (Garmin laps: "
            "auto 1 km, or workout/manual laps). Full mode returns splits[]: "
            "split_number, distance_km, pace (s/km), HR and max HR, GCT (ms), VO "
            "(cm), VR (%), power (W), stride (cm), cadence and max cadence (spm), "
            "elevation gain/loss (m), intensity_type and role_phase; _warnings "
            "flags laps without form metrics. To judge a single run, start from "
            "get_run_report; use this for lap-level detail it does not carry."
        ),
        params=SplitsStatsParams,
        handler=_get_splits_comprehensive,
        cli_group="splits",
        cli_name="comprehensive",
        field_descriptions={
            "statistics_only": (
                "If true, return only {mean, median, std, min, max} per metric "
                "(12 metrics) over all laps instead of per-lap rows: unweighted, "
                "the short final lap included, and a metric with no data reads "
                "0.0. Default: false"
            )
        },
    ),
    ToolDef(
        name="get_interval_analysis",
        description=(
            "Classify each lap of one activity as work/recovery/warmup/cooldown/"
            "steady from its Garmin intensity_type (INTERVAL, RECOVERY, ...; laps "
            "recorded as ACTIVE, including [MCP] workout steps, read as steady). "
            "Returns segments[] (per lap: times, duration, pace in decimal min/km, "
            "HR, GCT, VO, VR), work_recovery_comparison ({} unless both work and "
            "recovery laps exist) and fatigue_indicators (last minus first work "
            "lap). Missing values count as 0."
        ),
        params=IntervalAnalysisParams,
        handler=_get_interval_analysis,
        cli_group="splits",
        cli_name="interval-analysis",
    ),
]


SPLITS_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in SPLITS_TOOLS}
