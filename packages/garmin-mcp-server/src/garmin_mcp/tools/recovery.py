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


class GetWellnessBaselineDeviationParams(BaseModel):
    """Arguments for ``get_wellness_baseline_deviation``."""

    date: str | None = Field(
        default=None,
        description=(
            "Target day as YYYY-MM-DD. Omit to use the latest day in " "daily_wellness."
        ),
    )
    window_days: int = Field(
        default=30,
        description=(
            "Trailing window length in days used to build the personal baseline "
            "band (today excluded; default 30)."
        ),
    )


class GetLongRunRecoveryCostParams(BaseModel):
    """Arguments for ``get_long_run_recovery_cost``."""

    activity_id: int = Field(
        description="Activity ID of the run whose next-morning cost to judge.",
    )


class GetEnergyBalanceParams(BaseModel):
    """Arguments for ``get_energy_balance``."""

    end_date: str | None = Field(
        default=None,
        description=(
            "Last day of the window as YYYY-MM-DD. Omit to use yesterday (the "
            "last closed day)."
        ),
    )
    window_days: int = Field(
        default=7, description="Window length in days (default: 7)."
    )
    calibration_days: int = Field(
        default=28,
        description=(
            "Weight-calibration window in days ending at end_date (default: 28)."
        ),
    )


def _get_recovery_trend(reader: GarminDBReader, p: GetRecoveryTrendParams) -> Any:
    return reader.get_recovery_trend(p.weeks)


def _get_recovery_status(reader: GarminDBReader, p: GetRecoveryStatusParams) -> Any:
    return reader.get_recovery_status(p.date)


def _get_wellness_baseline_deviation(
    reader: GarminDBReader, p: GetWellnessBaselineDeviationParams
) -> Any:
    return reader.get_wellness_baseline_deviation(p.date, p.window_days)


def _get_long_run_recovery_cost(
    reader: GarminDBReader, p: GetLongRunRecoveryCostParams
) -> Any:
    return reader.get_long_run_recovery_cost(p.activity_id)


def _get_energy_balance(reader: GarminDBReader, p: GetEnergyBalanceParams) -> Any:
    return reader.get_energy_balance(
        end_date=p.end_date,
        window_days=p.window_days,
        calibration_days=p.calibration_days,
    )


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
            "body_battery_high, sleep_score, sleep_seconds (how long the night "
            "lasted, as opposed to how good it was; all null-safe)."
        ),
        params=GetRecoveryStatusParams,
        handler=_get_recovery_status,
        cli_group="physiology",
        cli_name="recovery-status",
    ),
    ToolDef(
        name="get_wellness_baseline_deviation",
        description=(
            "Judge today's HRV / Training Readiness / resting HR against the "
            "athlete's own rolling personal baseline band (mean +/- SD over the "
            "trailing window, default 30 days) from daily_wellness -- a "
            "per-individual early warning, not an absolute threshold (defaults to "
            "the latest day; pass date=YYYY-MM-DD for a specific day). Returns "
            "date, an hrv / readiness / rhr block each with mean, std, today, "
            "z=(today-mean)/std, flag ('low' when z<-1, 'high' when z>+1, else "
            "'within'; 'insufficient' with null stats when <7 non-null samples), "
            "adverse (true in the unfavorable direction -- low HRV/readiness or "
            "high RHR), and n, plus overall_flag (true when any metric is in an "
            "adverse deviation). All fields are null-safe (device-off days are "
            "skipped)."
        ),
        params=GetWellnessBaselineDeviationParams,
        handler=_get_wellness_baseline_deviation,
        cli_group="physiology",
        cli_name="wellness-baseline",
    ),
    ToolDef(
        name="get_long_run_recovery_cost",
        description=(
            "Judge what one run cost over the following two mornings: joins the "
            "activity to the daily_wellness rows of d+1 / d+2 and compares them "
            "with the athlete's own trailing 14-day median (run day excluded). "
            "Three criteria: 'rhr_two_day' (resting HR >=+2 bpm over baseline on "
            "BOTH mornings -- a single elevated morning is the normal price of a "
            "long run; with no d+2 row it needs >=+3 on d+1 alone), 'readiness' "
            "(d+1 Training Readiness <35) and 'hrv' (d+1 overnight HRV <=-15% vs "
            "baseline). cost_flag is true when >=2 of the 3 fire -- one lone "
            "marker is noise. Returns activity_id, activity_date, distance_km, "
            "avg_heart_rate, temperature_c, baseline (rhr_median, hrv_median, n), "
            "d1 (rhr, rhr_delta, hrv, hrv_delta_pct, readiness, sleep_hours, "
            "body_battery_low), d2 (rhr, rhr_delta), criteria [{name, fired, "
            "value, threshold}], criteria_fired, cost_flag, insufficient_data "
            "(missing d+1 row or <5 baseline RHR samples -- cost_flag is then "
            "false) and a short Japanese reason_ja. Returns null for an unknown "
            "activity. No distance floor is applied; the thresholds were "
            "backtested on runs >=15 km, where the rule fires on the two 2026 "
            "injury-trigger long runs and on none of the ladder long runs."
        ),
        params=GetLongRunRecoveryCostParams,
        handler=_get_long_run_recovery_cost,
        cli_group="physiology",
        cli_name="long-run-recovery-cost",
    ),
    ToolDef(
        name="get_energy_balance",
        description=(
            "Get the logged energy balance (food intake from MyFitnessPal via "
            "Garmin minus Garmin total expenditure) over a window (default the "
            "7 days ending yesterday) and judge it against the current "
            "training block's weight_mode. Every day carries intake_status "
            "(no_data / in_progress / pending / not_logged / "
            "athlete_reported_incomplete / suspect_low / provisional / "
            "settled) and expenditure_status (no_data / in_progress / "
            "unsynced / low_wear / ok); only settled/provisional intake with "
            "ok expenditure is averaged and missing days are never imputed. "
            "Returns end_date, as_of, window_days, days [{date, intake_kcal, "
            "expenditure_kcal, balance_kcal, intake_status, "
            "expenditure_status, used, in_window, confirmation}], window "
            "{status ok/insufficient/no_logging, paired_days, required_days "
            "(5 of every 7), mean_intake_kcal, mean_expenditure_kcal, "
            "mean_balance_kcal, provisional_days, excluded [{date, reason}]}, "
            "logging {first_logged_date, last_logged_date, "
            "days_since_last_log, lapsed (3+ closed days unlogged)}, target "
            "{weight_mode, block_id, crosses_block_boundary, band_kcal "
            "(維持 0 / 絞る -350..-250, widened by 150), verdict "
            "deeper_than_target / within_target / shallower_than_target, "
            "reason, basis='logged', calibration_status}, calibration over "
            "calibration_days (needs 21 paired days and 10 weigh-ins; Theil-Sen "
            "weight slope x 7700 kcal/kg with a 90% CI: consistent / "
            "logged_deficit_exceeds_weight / logged_deficit_below_weight / "
            "insufficient, plus notes -- values are never corrected), and "
            "weight {recent_median_kg, n_weighins, slope_kg_per_week}."
        ),
        params=GetEnergyBalanceParams,
        handler=_get_energy_balance,
        cli_group="physiology",
        cli_name="energy-balance",
    ),
]


RECOVERY_TOOLS_BY_NAME: dict[str, ToolDef] = {d.name: d for d in RECOVERY_TOOLS}
