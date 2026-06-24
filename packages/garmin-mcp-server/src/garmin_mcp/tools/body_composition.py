"""Body-composition trend tool definition (#501).

Exposes ``get_body_composition_trend``: decomposes the trailing-window weight
change into fat / lean components and derives lean-mass power-to-weight. Reuses
already-ingested ``body_composition`` + ``lactate_threshold`` data (no new
ingest). Delegates to ``GarminDBReader.get_body_composition_trend``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetBodyCompositionTrendParams(BaseModel):
    """Arguments for ``get_body_composition_trend``."""

    weeks: int = Field(
        default=12,
        description="Trailing window length in weeks to analyze (default: 12).",
    )


def _get_body_composition_trend(
    reader: GarminDBReader, p: GetBodyCompositionTrendParams
) -> Any:
    return reader.get_body_composition_trend(p.weeks)


BODY_COMPOSITION_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_body_composition_trend",
        description=(
            "Get the body-composition trend over the trailing window (default 12 "
            "weeks). Decomposes the weight change between the first and last "
            "measurement into fat-mass and lean-mass components. Returns weeks, "
            "a date-ascending series ([{date, weight_kg, fat_mass, lean_mass}]; "
            "fat_mass/lean_mass null when body fat unrecorded), a change block "
            "(delta_weight, delta_fat, delta_lean, lean_loss_ratio, "
            "muscle_loss_warning -- true when >40% of the lost weight is lean "
            "mass, flagging leg-durability/injury risk), and lean_pwr (lean-mass "
            "power-to-weight = latest functional_threshold_power / lean mass; "
            "null when body fat or FTP is missing)."
        ),
        params=GetBodyCompositionTrendParams,
        handler=_get_body_composition_trend,
        cli_group="physiology",
        cli_name="body-composition-trend",
    ),
]


BODY_COMPOSITION_TOOLS_BY_NAME: dict[str, ToolDef] = {
    d.name: d for d in BODY_COMPOSITION_TOOLS
}
