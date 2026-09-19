"""Single-run report tool definition (#1250).

``get_run_report`` is the one deterministic answer to "how did this run go?":
the plan verdict, every metric against the athlete's own normal range, the
turning points of the run and the conditions it was run in. The Web page, the
run-note agent and the coaching skills all read this same payload, so the tool
is a thin delegation to ``GarminDBReader.get_run_report`` -- no statistics live
here.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.registry import ToolDef

logger = logging.getLogger(__name__)


class GetRunReportParams(BaseModel):
    """Arguments for ``get_run_report``."""

    activity_id: int = Field(
        description="Activity ID to build the deterministic run report for.",
    )


def _get_run_report(reader: GarminDBReader, p: GetRunReportParams) -> Any:
    return reader.get_run_report(p.activity_id)


RUN_REPORT_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_run_report",
        description=(
            "Get the deterministic report for one run: everything the "
            "single-run page and the run note are built from, in one call. "
            "Returns activity_id, activity_date, intensity_category, headline "
            "(plan_label, flag_count, flag_labels -- adverse signals only), "
            "plan (verdict ✅/🟡/🔴 against the day's prescription, its title, "
            "per-axis checks with target/actual/on_plan, and hr_ceiling "
            "{bpm, seconds_over, pct_over}; null when the day had no "
            "prescription), signals (per metric: today, expected, the "
            "athlete's own normal_low/normal_high, z, status "
            "within/edge/outside/insufficient, adverse, streak, n, reason), "
            "zones (HR zone percentages), moments (2-5 deterministic turning "
            "points, each with a label_ja and a unit of km or step, real "
            "positions km_from/km_to + t_from_s/t_to_s, and facts), flow (the "
            "series the chart draws: axis distance/time, total_km, total_s, "
            "segments, steps and the fragment count), recurrence (moment "
            "kinds that keep happening at the same point of the run), phases "
            "(warmup/run/recovery/cooldown pace and HR), conditions "
            "(temp_c, humidity_pct, "
            "wind_mps, terrain, elevation_gain_m), vs_previous (delta chips "
            "against the previous same-family run), next_run_target (what the "
            "next run of this kind should look like) and next_session (what "
            "the athlete actually does next: date, days_ahead, session_type, "
            "title, target_km/target_minutes, hr_low/hr_high and whether it "
            "came from the plan, the long-run ladder or a projection). "
            "Returns null when the activity does not exist."
        ),
        params=GetRunReportParams,
        handler=_get_run_report,
        cli_group="analysis",
        cli_name="run-report",
    ),
]


RUN_REPORT_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in RUN_REPORT_TOOLS}
