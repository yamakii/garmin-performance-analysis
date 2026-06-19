"""Race domain tool definitions.

Exposes the rescued ``VDOTCalculator`` (#60) as a single ``get_race_readiness``
tool: current VDOT, VDOT-based race-time predictions, and the gap to the active
race goal.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetRaceReadinessParams(BaseModel):
    """Arguments for ``get_race_readiness``."""

    user_id: str = Field(
        default="default", description="Profile owner identifier (default: 'default')"
    )
    lookback_weeks: int = Field(
        default=8,
        description="Lookback window (weeks) for the fitness assessment (default: 8)",
    )


def _get_race_readiness(reader: GarminDBReader, p: GetRaceReadinessParams) -> Any:
    return reader.get_race_readiness(p.user_id, p.lookback_weeks)


RACE_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_race_readiness",
        description=(
            "Get race readiness: the athlete's current VDOT (from recent "
            "fitness), VDOT-based race-time predictions (5k/10k/half/full in "
            "seconds), the active race goal (priority A / active preferred, else "
            "the nearest future race), and a progress block with the predicted "
            "goal-distance time, gap to target (seconds; positive = behind "
            "target), pace gap (sec/km), weeks remaining, and a status "
            "(ahead/on_track/behind). Returns empty predictions when no VDOT can "
            "be derived and a null goal/progress when no goal is registered."
        ),
        params=GetRaceReadinessParams,
        handler=_get_race_readiness,
        cli_group="race",
        cli_name="readiness",
    ),
]


RACE_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in RACE_TOOLS}
