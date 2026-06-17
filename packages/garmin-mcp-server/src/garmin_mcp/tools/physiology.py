"""Physiology domain tool definitions (pilot for the single-source registry).

Descriptions are copied verbatim from the previous hand-written schemas in
``tool_schemas.py`` to guarantee byte-for-byte MCP parity.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from garmin_mcp.tools.registry import ToolDef


class ActivityIdParams(BaseModel):
    """Single ``activity_id`` argument shared by most physiology tools."""

    activity_id: int


class FormBaselineTrendParams(BaseModel):
    """Arguments for ``get_form_baseline_trend``."""

    activity_id: int
    activity_date: str = Field(description="Activity date in YYYY-MM-DD format")
    user_id: str = Field(default="default", description="User ID (default: 'default')")
    condition_group: str = Field(
        default="flat_road", description="Condition group (default: 'flat_road')"
    )


PHYSIOLOGY_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_form_efficiency_summary",
        description=(
            "Get form efficiency summary (GCT, VO, VR metrics) from "
            "form_efficiency table"
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_form_efficiency_summary(p.activity_id),
        cli_group="physiology",
        cli_name="form-efficiency",
    ),
    ToolDef(
        name="get_form_evaluations",
        description=(
            "Get pace-corrected form evaluation results (expected values, actual "
            "values, scores, star ratings, evaluation texts)"
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_form_evaluations(p.activity_id),
        cli_group="physiology",
        cli_name="form-evaluations",
    ),
    ToolDef(
        name="get_form_baseline_trend",
        description=(
            "Get form baseline trend (1-month coefficient comparison for "
            "form_trend analysis)"
        ),
        params=FormBaselineTrendParams,
        handler=lambda r, p: r.physiology.get_form_baseline_trend(
            p.activity_id,
            p.activity_date,
            user_id=p.user_id,
            condition_group=p.condition_group,
        ),
        cli_group="physiology",
        cli_name="form-baseline-trend",
    ),
    ToolDef(
        name="get_hr_efficiency_analysis",
        description=(
            "Get HR efficiency analysis (zone distribution, training type) from "
            "hr_efficiency table"
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_hr_efficiency_analysis(p.activity_id),
        cli_group="physiology",
        cli_name="hr-efficiency",
    ),
    ToolDef(
        name="get_heart_rate_zones_detail",
        description=(
            "Get heart rate zones detail (boundaries, time distribution) from "
            "heart_rate_zones table"
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_heart_rate_zones_detail(p.activity_id),
        cli_group="physiology",
        cli_name="heart-rate-zones",
    ),
    ToolDef(
        name="get_vo2_max_data",
        description="Get VO2 max data (precise value, fitness age, category) from vo2_max table",
        params=ActivityIdParams,
        handler=lambda r, p: r.get_vo2_max_data(p.activity_id),
        cli_group="physiology",
        cli_name="vo2-max",
    ),
    ToolDef(
        name="get_lactate_threshold_data",
        description="Get lactate threshold data (HR, speed, power) from lactate_threshold table",
        params=ActivityIdParams,
        handler=lambda r, p: r.get_lactate_threshold_data(p.activity_id),
        cli_group="physiology",
        cli_name="lactate-threshold",
    ),
]


PHYSIOLOGY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in PHYSIOLOGY_TOOLS}
