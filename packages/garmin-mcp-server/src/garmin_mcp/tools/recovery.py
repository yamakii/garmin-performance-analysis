"""Recovery-trend tool definition (#499).

Exposes ``get_recovery_trend``: derives a resting-HR trend (7-day vs 30-day
median) and an HRV recovery status (consecutive nights below baseline) from the
already-ingested ``daily_wellness`` table (no new ingest). Delegates to
``GarminDBReader.get_recovery_trend``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetRecoveryTrendParams(BaseModel):
    """Arguments for ``get_recovery_trend``."""

    weeks: int = Field(
        default=8,
        description="Trailing window length in weeks to analyze (default: 8).",
    )


class GetRecoveryStatusParams(BaseModel):
    """Arguments for ``get_recovery_status``."""

    date: str | None = Field(
        default=None,
        description=(
            "Target day as YYYY-MM-DD. Omit to use the latest day in " "daily_wellness."
        ),
    )


def _get_recovery_trend(reader: GarminDBReader, p: GetRecoveryTrendParams) -> Any:
    return reader.get_recovery_trend(p.weeks)


def _get_recovery_status(reader: GarminDBReader, p: GetRecoveryStatusParams) -> Any:
    return reader.get_recovery_status(p.date)


RECOVERY_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_recovery_trend",
        description=(
            "Get the RHR / HRV recovery trend over the trailing window (default "
            "8 weeks) from daily_wellness. Returns weeks, an rhr block "
            "(median_7d, median_30d, rhr_trend -- 'improving' when the 7-day "
            "median is >=2 bpm below the 30-day median, 'fatigued' when >=3 bpm "
            "above, else 'stable'), an hrv block (latest_ms, status, "
            "hrv_below_baseline_days, under_recovery -- true when >=2 consecutive "
            "nights are below HRV baseline; AND this with a high get_acwr to flag "
            "over-training), and a date-ascending series ([{date, resting_hr, "
            "hrv_overnight_ms}]). Medians / HRV fields are null when data is "
            "missing (device-off days are skipped)."
        ),
        params=GetRecoveryTrendParams,
        handler=_get_recovery_trend,
        cli_group="physiology",
        cli_name="recovery-trend",
    ),
    ToolDef(
        name="get_recovery_status",
        description=(
            "Get today's morning go/no-go recovery status from daily_wellness "
            "(defaults to the latest day; pass date=YYYY-MM-DD for a specific "
            "day). Synthesizes Training Readiness, Body Battery and sleep score "
            "with the HRV under_recovery flag into a recommendation: 'rest' / "
            "'easy' when readiness<50 or sleep<50 or HRV is under-recovered "
            "(>=2 nights below baseline), 'quality' (tempo allowed) when "
            "readiness>=75 and HRV is normal, else 'moderate'. Device-off days "
            "(no readiness and no sleep) return recommendation='unknown' with a "
            "'go by feel' reason. Returns date, recommendation, score (mean of "
            "available markers), reasons, and the raw training_readiness, "
            "body_battery_high, sleep_score (all null-safe)."
        ),
        params=GetRecoveryStatusParams,
        handler=_get_recovery_status,
        cli_group="physiology",
        cli_name="recovery-status",
    ),
]


RECOVERY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in RECOVERY_TOOLS}
