"""Performance domain tool definitions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ACTIVITY_ID_DESCRIPTION, ToolDef


class ActivityIdParams(BaseModel):
    """Single ``activity_id`` argument shared by the performance tools."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)


class ObjectiveFitnessParams(BaseModel):
    """Arguments for the objective fitness curve tool."""

    window_days: int = Field(
        default=90,
        description="Rolling window in days for the best-effort maximum (default 90)",
    )


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
        description=(
            "Within-run pacing summary for one activity: pace_consistency "
            "(coefficient of variation of representative run-lap paces, a "
            "fraction), hr_drift_percentage (half-vs-half decoupling for steady "
            "runs, rep-matched drift for intervals) and avg_pace (s/km) / avg_hr "
            "per phase (warmup, run, cooldown, plus recovery for intervals). "
            "Null when missing. get_activity_durability gives the time-series "
            "decoupling."
        ),
        params=ActivityIdParams,
        handler=_get_performance_trends,
        cli_group="performance",
        cli_name="trends",
    ),
    ToolDef(
        name="get_weather_data",
        description=(
            "Weather for one activity from Garmin's activity weather record (an "
            "external weather station's observation near the start time), not "
            "the watch's body-warmed temperature sensor. Returns temperature_c, "
            "temperature_f, humidity (%), wind_speed_ms and wind_direction "
            "(compass point). One snapshot per run; fields are null when Garmin "
            "had no weather, and the result is null for an unknown activity."
        ),
        params=ActivityIdParams,
        handler=_get_weather_data,
        cli_group="performance",
        cli_name="weather",
    ),
    ToolDef(
        name="prefetch_activity_context",
        description=(
            "Pre-fetch the context a run report does not carry, in a single "
            "call: training_type, the shoe worn (gear), similar_workouts "
            "(earlier runs only), the "
            "long_run_gate verdict (runs >= 10 km) and the prescription vs "
            "actual layer (that day's prescription, week_position, "
            "previous_same_type + vs_previous and morning_wellness). The run "
            "itself (plan vs actual and its verdict, signals, scenes, "
            "conditions) is get_run_report; weather, "
            "HR zones and form have their own tools. Auto-generates the form "
            "baseline for the activity's month (and prior month) if missing."
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
            "VO2max and the optimism gap. Returns objective_curve "
            "[{date, vdot, source_distance_km}] ascending by run day (best "
            "contiguous 2 / 5 / 10 km efforts), garmin_vo2max [{date, value}] "
            "ascending, and optimism_gap {garmin_vdot, objective_vdot, gap_vdot, "
            "gap_speed_mps, gap_pace_sec_per_km}, or null when either series is "
            "empty. get_race_readiness reads the latest objective VDOT per "
            "distance bucket from this curve."
        ),
        params=ObjectiveFitnessParams,
        handler=_get_objective_fitness_curve,
        cli_group="performance",
        cli_name="objective-fitness-curve",
    ),
]


PERFORMANCE_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in PERFORMANCE_TOOLS}
