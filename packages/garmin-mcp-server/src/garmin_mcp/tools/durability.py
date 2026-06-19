"""Durability (cardiac-decoupling) tool definitions.

Exposes long-run durability as two tools: ``get_activity_durability`` (one
activity's first-half vs second-half decoupling) and ``get_durability_trend``
(the decoupling trend across long runs in a date window). Both delegate to
``DurabilityReader``.

v1 measures cardiac decoupling and pace fade only; second-half *form* decay
(GCT/VO/VR) is already covered per-activity by #61 and is out of scope here.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetActivityDurabilityParams(BaseModel):
    """Arguments for ``get_activity_durability``."""

    activity_id: int = Field(
        description="Activity ID to compute first-half vs second-half decoupling for.",
    )


class GetDurabilityTrendParams(BaseModel):
    """Arguments for ``get_durability_trend``."""

    start_date: str = Field(
        description="Inclusive window start date (YYYY-MM-DD).",
    )
    end_date: str = Field(
        description="Inclusive window end date (YYYY-MM-DD).",
    )
    min_distance_km: float = Field(
        default=15.0,
        description=(
            "Minimum total_distance_km for an activity to qualify as a long run "
            "(default: 15.0). Shorter runs are excluded."
        ),
    )


def _get_activity_durability(
    reader: GarminDBReader, p: GetActivityDurabilityParams
) -> Any:
    return reader.get_activity_durability(p.activity_id)


def _get_durability_trend(reader: GarminDBReader, p: GetDurabilityTrendParams) -> Any:
    return reader.get_durability_trend(p.start_date, p.end_date, p.min_distance_km)


DURABILITY_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_activity_durability",
        description=(
            "Get one activity's cardiac decoupling: the second-half vs first-half "
            "HR/speed efficiency ratio (split at the time-series timestamp "
            "midpoint). Returns activity_id, activity_date, distance_km, "
            "decoupling_pct ((back HR/speed)/(front HR/speed)-1; >5% suggests "
            "insufficient aerobic durability), and pace_fade_pct (back/front pace "
            "ratio). Returns null when HR or speed data is missing."
        ),
        params=GetActivityDurabilityParams,
        handler=_get_activity_durability,
        cli_group="durability",
        cli_name="activity",
    ),
    ToolDef(
        name="get_durability_trend",
        description=(
            "Get the longitudinal cardiac-decoupling trend across long runs in a "
            "date window. Only activities with total_distance_km >= "
            "min_distance_km (default 15) are included. Returns an activities "
            "array (per-activity durability, date ascending) and a trend block "
            "with decoupling_slope_per_day (regressed on elapsed days), "
            "data_points, and direction (improving when decoupling falls / "
            "worsening / stable / insufficient_data)."
        ),
        params=GetDurabilityTrendParams,
        handler=_get_durability_trend,
        cli_group="durability",
        cli_name="trend",
    ),
]


DURABILITY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in DURABILITY_TOOLS}
