"""Training-load and injury-precursor tool definitions.

Exposes the distance-based Acute:Chronic Workload Ratio (ACWR) as ``get_acwr``
(current snapshot) and ``get_load_trend`` (weekly history) -- both delegate to
``TrainingLoadReader`` and are HR-independent (distance only) -- plus the two
deterministic gates built on top of the same ``activities`` history:
``get_injury_risk`` (composite score) and ``get_post_event_window`` (the
21-day protection window after a race).
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


class GetPostEventWindowParams(BaseModel):
    """Arguments for ``get_post_event_window``."""

    date: str | None = Field(
        default=None,
        description=(
            "Reference day (YYYY-MM-DD) the protection window is evaluated as "
            "of. Defaults to the latest activity_date."
        ),
    )


def _get_acwr(reader: GarminDBReader, p: GetAcwrParams) -> Any:
    return reader.get_acwr(p.end_date)


def _get_load_trend(reader: GarminDBReader, p: GetLoadTrendParams) -> Any:
    return reader.get_load_trend(p.lookback_weeks, p.end_date)


def _get_injury_risk(reader: GarminDBReader, p: GetInjuryRiskParams) -> Any:
    return reader.get_injury_risk(p.date)


def _get_post_event_window(reader: GarminDBReader, p: GetPostEventWindowParams) -> Any:
    return reader.get_post_event_window(p.date)


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
            "backfill). Fuses seven deterministic signals: ACWR (weight 0.25; "
            "0.8-1.3 is the safe zone, 1.5 = 50%, 1.8+ = 100%), the symptom-log "
            "rule (0.25), the post-race protection window (0.15; inside the "
            "window green = 25%, yellow = 60%, red = 100%), the latest long "
            "run's next-morning recovery cost (0.10; criteria fired / 3), "
            "worsening durability trend (0.10), personal wellness-baseline "
            "deviation of HRV/readiness/RHR (0.10), and trailing-14-day form "
            "anomalies (0.05). Missing signals are dropped and the rest "
            "renormalized; when all are missing returns {insufficient_data: "
            "true}. Bands: <30 low / 30-60 moderate / >60 high. Defaults to the "
            "latest activity_date."
        ),
        params=GetInjuryRiskParams,
        handler=_get_injury_risk,
        cli_group="load",
        cli_name="injury-risk",
    ),
    ToolDef(
        name="get_post_event_window",
        description=(
            "Get the 21-day protection window after the last race or "
            "comparably big stimulus, and whether the long runs since then "
            "stayed under the pre-event ceiling. The event comes from the race "
            "calendar first (athlete_goals at any status, plus kind='race' "
            "steps of the block's long-run ladder, mapped to that week's "
            "Sunday); a >=18 km run at or above its own Garmin zone-3 lower "
            "boundary is only a fallback proxy and never overrides a calendar "
            "event on the same day (a cold-weather half can average 141 bpm). "
            "ceiling_km = the longest run in the 56 days before the event. "
            "Verdicts: no_event / green (outside the window, or at or under "
            "the ceiling) / yellow (over the ceiling) / red (over it by more "
            "than 10%) / insufficient_data (in window, no ceiling). Returns "
            "date, last_event {date, source, label, activity_id}, "
            "days_since_event, in_window, ceiling_km, longest_since_km, "
            "longest_since_activity_id, overshoot_pct, verdict and a Japanese "
            "reason_ja. Defaults to the latest activity_date."
        ),
        params=GetPostEventWindowParams,
        handler=_get_post_event_window,
        cli_group="load",
        cli_name="post-event-window",
    ),
]


LOAD_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in LOAD_TOOLS}
