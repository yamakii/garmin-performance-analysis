"""Performance domain tool definitions.

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef


class ActivityIdParams(BaseModel):
    """Single ``activity_id`` argument shared by the performance tools."""

    activity_id: int


class ObjectiveFitnessParams(BaseModel):
    """Arguments for the objective fitness curve tool."""

    window_days: int = 90


def _get_performance_trends(reader: GarminDBReader, p: ActivityIdParams) -> Any:
    return reader.get_performance_trends(p.activity_id)


def _get_objective_fitness_curve(
    reader: GarminDBReader, p: ObjectiveFitnessParams
) -> Any:
    return reader.fitness_curve.get_objective_fitness_curve(window_days=p.window_days)


def _get_weather_data(reader: GarminDBReader, p: ActivityIdParams) -> Any:
    return reader.get_weather_data(p.activity_id)


def _prefetch_activity_context(reader: GarminDBReader, p: ActivityIdParams) -> Any:
    from garmin_mcp.scripts.prefetch_activity_context import prefetch_activity_context

    return prefetch_activity_context(p.activity_id)


PERFORMANCE_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_performance_trends",
        description="Get performance trends data (pace consistency, HR drift, phase analysis)",
        params=ActivityIdParams,
        handler=_get_performance_trends,
        cli_group="performance",
        cli_name="trends",
    ),
    ToolDef(
        name="get_weather_data",
        description="Get weather data (temperature, humidity, wind) from activity",
        params=ActivityIdParams,
        handler=_get_weather_data,
        cli_group="performance",
        cli_name="weather",
    ),
    ToolDef(
        name="prefetch_activity_context",
        description=(
            "Pre-fetch shared activity context for analysis agents. Returns "
            "training_type, weather, terrain, HR efficiency (zone_percentages), "
            "form evaluation scores, phase structure, and planned workout in a "
            "single call. Auto-generates the form baseline for the activity's "
            "month (and prior month) if missing."
        ),
        params=ActivityIdParams,
        handler=_prefetch_activity_context,
        cli_group="performance",
        cli_name="prefetch-context",
    ),
    ToolDef(
        name="get_objective_fitness_curve",
        description=(
            "Objective (non-optimistic) fitness curve: rolling 90-day max "
            "best-effort performance VDOT from splits, side-by-side with Garmin "
            "VO2max and the optimism gap."
        ),
        params=ObjectiveFitnessParams,
        handler=_get_objective_fitness_curve,
        cli_group="performance",
        cli_name="objective-fitness-curve",
    ),
]


PERFORMANCE_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in PERFORMANCE_TOOLS}
