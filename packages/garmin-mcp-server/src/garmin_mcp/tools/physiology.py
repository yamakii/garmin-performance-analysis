"""Physiology domain tool definitions (pilot for the single-source registry)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from garmin_mcp.tools.registry import ACTIVITY_ID_DESCRIPTION, ToolDef


class ActivityIdParams(BaseModel):
    """Single ``activity_id`` argument shared by most physiology tools."""

    activity_id: int = Field(description=ACTIVITY_ID_DESCRIPTION)


class FormBaselineTrendParams(BaseModel):
    """Arguments for ``get_form_baseline_trend``."""

    activity_id: int = Field(
        description="Garmin activity ID; echoed only (the lookup uses activity_date)"
    )
    activity_date: str = Field(
        description=(
            "Date (YYYY-MM-DD) whose baseline period is compared with the one a "
            "month earlier"
        )
    )
    user_id: str = Field(
        default="default", description="Baseline owner (default: 'default')"
    )
    condition_group: str = Field(
        default="flat_road",
        description=(
            "Baseline condition group (default: 'flat_road', the group the "
            "baseline scripts train)"
        ),
    )


PHYSIOLOGY_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_form_efficiency_summary",
        description=(
            "Get raw form metric statistics (GCT, VO, VR averages, min/max, "
            "std) from the form_efficiency table. NOT AUTHORITATIVE for "
            "judging form: the star ratings here are absolute bands with no "
            "pace term, so the same runner reads worse at slow paces purely "
            "because ground contact and vertical ratio scale with speed. Use "
            "get_form_evaluations for the pace-corrected verdict, and "
            "get_form_baseline_trend for longitudinal comparison."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_form_efficiency_summary(p.activity_id),
        cli_group="physiology",
        cli_name="form-efficiency",
    ),
    ToolDef(
        name="get_form_evaluations",
        description=(
            "Pace-corrected form inputs for one activity: for GCT (ms), VO (cm), "
            "VR (%) and cadence (spm), the actual value, the value expected at "
            "that pace from the athlete's own baseline, the delta, a star score "
            "and evaluation text; power efficiency (W, W/kg, actual vs expected "
            "speed, a self-baseline label); integrated_score, training_mode and "
            "overall score/stars. Null when not evaluated. Stars are legacy "
            "display values; judge a run with get_run_report."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_form_evaluations(p.activity_id),
        cli_group="physiology",
        cli_name="form-evaluations",
    ),
    ToolDef(
        name="get_form_baseline_trend",
        description=(
            "Compare the athlete's form-baseline model coefficients for the "
            "period containing activity_date with the period one month earlier. "
            "Returns success and metrics keyed gct/vo/vr/cadence/power, each with "
            "current and previous {coef_d, coef_b, power_a, power_b, period} and "
            "deltas (delta_d/delta_b for the pace models, delta_power_a/"
            "delta_power_b for power). success=false with an error when either "
            "period has no baseline."
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
            "HR-zone summary for one activity, computed at ingest from Garmin's "
            "native zone times: zone_percentages zone1-zone5 (% of time), "
            "primary_zone, training_type (Garmin training-effect label, "
            "lowercased), rule-based labels zone_distribution_rating, "
            "hr_stability, aerobic_efficiency and training_quality, and flags "
            "zone2_focus (>60% Z2) and zone4_threshold_work (>20% Z4-5). Null when "
            "missing. Zone boundaries: get_heart_rate_zones_detail."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_hr_efficiency_analysis(p.activity_id),
        cli_group="physiology",
        cli_name="hr-efficiency",
    ),
    ToolDef(
        name="get_heart_rate_zones_detail",
        description=(
            "Garmin native heart-rate zones recorded with one activity: zones[] "
            "with zone_number 1-5, low_boundary and high_boundary (bpm), "
            "time_in_zone_seconds and zone_percentage. Boundaries are the zone "
            "settings in force for that run; high_boundary is the next zone's low "
            "minus 1, and null for zone 5, which has no upper bound. Null when "
            "missing."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_heart_rate_zones_detail(p.activity_id),
        cli_group="physiology",
        cli_name="heart-rate-zones",
    ),
    ToolDef(
        name="get_vo2_max_data",
        description=(
            "Garmin's running VO2max estimate for one activity: precise_value and "
            "rounded value (ml/kg/min) and date (Garmin calendar date of the "
            "estimate). When the activity has no row, falls back to the latest estimate dated on or "
            "before the activity. Null when none exists."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_vo2_max_data(p.activity_id),
        cli_group="physiology",
        cli_name="vo2-max",
    ),
    ToolDef(
        name="get_lactate_threshold_data",
        description=(
            "Garmin's lactate-threshold values fetched with one activity: "
            "heart_rate (bpm), speed_mps (m/s), date_hr (when Garmin last updated "
            "the HR/speed threshold), functional_threshold_power (W), "
            "power_to_weight (W/kg), weight and date_power. Null when that "
            "activity has no row; there is no fallback to other activities. These "
            "are Garmin's auto-estimates as of the fetch."
        ),
        params=ActivityIdParams,
        handler=lambda r, p: r.get_lactate_threshold_data(p.activity_id),
        cli_group="physiology",
        cli_name="lactate-threshold",
    ),
]


PHYSIOLOGY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in PHYSIOLOGY_TOOLS}
