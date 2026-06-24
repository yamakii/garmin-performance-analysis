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


def _get_recovery_trend(reader: GarminDBReader, p: GetRecoveryTrendParams) -> Any:
    return reader.get_recovery_trend(p.weeks)


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
]


RECOVERY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in RECOVERY_TOOLS}
