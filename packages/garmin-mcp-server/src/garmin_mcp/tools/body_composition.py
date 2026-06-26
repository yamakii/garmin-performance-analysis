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


class GetWeightEconomyCouplingParams(BaseModel):
    """Arguments for ``get_weight_economy_coupling``."""

    weeks: int = Field(
        default=52,
        description="Trailing window length in weeks to analyze (default: 52).",
    )
    max_gap_days: int = Field(
        default=14,
        description=(
            "Maximum allowed absolute day gap between a run and the nearest "
            "body-composition weight measurement for the join (default: 14)."
        ),
    )


def _get_weight_economy_coupling(
    reader: GarminDBReader, p: GetWeightEconomyCouplingParams
) -> Any:
    return reader.get_weight_economy_coupling(
        weeks=p.weeks, max_gap_days=p.max_gap_days
    )


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
    ToolDef(
        name="get_weight_economy_coupling",
        description=(
            "Couple easy runs (default training_type=aerobic_base) with body "
            "weight and fit a longitudinal running-economy model over the "
            "trailing window (default 52 weeks). Joins each easy run to its "
            "nearest body_composition weight (within max_gap_days, default 14) "
            "and derives the efficiency factor EF = avg_speed_ms / "
            "avg_heart_rate, then fits EF ~ weight + days (+ VO2max fitness) by "
            "OLS. Returns weeks, n_runs_total, n_matched, weight_spread_kg, a "
            "model block (weight/days/fitness coefficients with p-values and "
            "VIF, R^2, delta_ef_per_5kg_loss effect size, collinearity_flag, "
            "note) reported as an association rather than a clean causal "
            "coefficient, a date-ascending series ([{activity_id, run_date, "
            "weight_kg, ef, weight_gap_days}]), and a note. When too few runs "
            "match for the regression, model is null and a reason string is "
            "included (no error raised)."
        ),
        params=GetWeightEconomyCouplingParams,
        handler=_get_weight_economy_coupling,
        cli_group="physiology",
        cli_name="weight-economy-coupling",
    ),
]


BODY_COMPOSITION_TOOLS_BY_NAME: dict[str, ToolDef] = {
    d.name: d for d in BODY_COMPOSITION_TOOLS
}
