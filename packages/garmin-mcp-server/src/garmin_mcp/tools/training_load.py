"""Training-load (ACWR) tool definitions.

Exposes the distance-based Acute:Chronic Workload Ratio (ACWR) as two tools:
``get_acwr`` (current snapshot) and ``get_load_trend`` (weekly history). Both
delegate to ``TrainingLoadReader`` and are HR-independent (distance only).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetAcwrParams(BaseModel):
    """Arguments for ``get_acwr``."""

    end_date: str | None = Field(
        default=None,
        description=(
            "Reference day (YYYY-MM-DD) the ACWR is computed as of. Defaults to "
            "the latest activity_date."
        ),
    )


class GetLoadTrendParams(BaseModel):
    """Arguments for ``get_load_trend``."""

    lookback_weeks: int = Field(
        default=12,
        description="Number of trailing weekly buckets to return (default: 12).",
    )
    end_date: str | None = Field(
        default=None,
        description=(
            "Reference day (YYYY-MM-DD) for the most recent week. Defaults to "
            "the latest activity_date."
        ),
    )


class GetInjuryRiskParams(BaseModel):
    """Arguments for ``get_injury_risk``."""

    date: str | None = Field(
        default=None,
        description=(
            "Reference day (YYYY-MM-DD) the injury-risk score is computed as of. "
            "Defaults to the latest activity_date."
        ),
    )


def _get_acwr(reader: GarminDBReader, p: GetAcwrParams) -> Any:
    return reader.get_acwr(p.end_date)


def _get_load_trend(reader: GarminDBReader, p: GetLoadTrendParams) -> Any:
    return reader.get_load_trend(p.lookback_weeks, p.end_date)


def _get_injury_risk(reader: GarminDBReader, p: GetInjuryRiskParams) -> Any:
    return reader.get_injury_risk(p.date)


LOAD_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_acwr",
        description=(
            "Get the distance-based Acute:Chronic Workload Ratio (ACWR), an "
            "injury-risk proxy. Daily load is the sum of total_distance_km; "
            "acute = the last-7-day load sum and chronic = the last-28-day load "
            "sum divided by 4 (weekly average). Returns acute_load_7d, "
            "chronic_load_28d_weekly, acwr (null when there is no chronic "
            "baseline), and a status (undertraining <0.8 / optimal 0.8-1.3 / "
            "caution 1.3-1.5 / high_risk >1.5 / insufficient_data). "
            "HR-independent: works even when avg_heart_rate is null."
        ),
        params=GetAcwrParams,
        handler=_get_acwr,
        cli_group="load",
        cli_name="acwr",
    ),
    ToolDef(
        name="get_load_trend",
        description=(
            "Get the weekly training-load and ACWR trend over the trailing "
            "lookback_weeks (default 12). Returns a weeks array (oldest to "
            "newest) with week_start, load_km (that week's total distance), acwr "
            "(null when there is no chronic baseline), and status. Distance-based "
            "and HR-independent."
        ),
        params=GetLoadTrendParams,
        handler=_get_load_trend,
        cli_group="load",
        cli_name="trend",
    ),
    ToolDef(
        name="get_injury_risk",
        description=(
            "Get a composite injury-risk score (0-100) with a low/moderate/high "
            "band and a per-factor breakdown, live-computed (no LLM, no "
            "backfill). Fuses four deterministic signals: ACWR (weight 0.40; "
            "0.8-1.3 is the safe zone, 1.5 = 50%, 1.8+ = 100%), worsening "
            "durability trend (0.25), personal wellness-baseline deviation of "
            "HRV/readiness/RHR (0.20), and trailing-14-day form anomalies "
            "(0.15). Missing signals are dropped and the rest renormalized; when "
            "all are missing returns {insufficient_data: true}. Bands: <30 low / "
            "30-60 moderate / >60 high. Defaults to the latest activity_date."
        ),
        params=GetInjuryRiskParams,
        handler=_get_injury_risk,
        cli_group="load",
        cli_name="injury-risk",
    ),
]


LOAD_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in LOAD_TOOLS}
