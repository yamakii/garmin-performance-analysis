"""Energy-balance day statuses, window mean, weight_mode verdict and calibration.

Pure functions over the facts stored by #1433 (``daily_energy`` +
``intake_confirmations``); issue #1434, Epic #1432. Every status is derived at
read time and never stored, and a day that cannot be used is excluded with its
reason -- a missing or doubtful day is never imputed.

Intake status (first match wins):

1. ``no_data`` -- no row.
2. ``in_progress`` -- the day is not over (``date >= as_of`` and the summary
   covers less than a full day).
3. ``pending`` -- the day is over but not settled, and intake is 0 / null
   (food may still be logged).
4. ``not_logged`` -- settled, and intake is 0 / null.
5. ``athlete_reported_incomplete`` -- the athlete said the log is incomplete.
6. ``suspect_low`` -- intake below ``SUSPECT_LOW_RATIO`` x the athlete's own
   median of settled logged days in the 28 days before (fallback: below the
   same ratio of ``bmr_kcal`` when fewer than ``MIN_OWN_BASELINE_DAYS`` such
   days exist). A ``complete`` confirmation lifts this status.
7. ``provisional`` -- logged but not yet settled.
8. ``settled``.

A confirmation is ignored when the intake changed after it was given
(``consumed_changed_at > confirmed_at``).

Expenditure status: ``no_data`` / ``in_progress`` / ``unsynced`` (closed day
covering less than a full day) / ``low_wear`` (awake + asleep + activity time
below ``MIN_WEAR_RATIO`` of the coverage) / ``ok``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from garmin_mcp.ingest.energy_fetcher import FULL_DAY_SECONDS, SETTLE_DAYS

IntakeStatus = Literal[
    "no_data",
    "in_progress",
    "pending",
    "not_logged",
    "athlete_reported_incomplete",
    "suspect_low",
    "provisional",
    "settled",
]
ExpenditureStatus = Literal["no_data", "in_progress", "unsynced", "low_wear", "ok"]

MIN_WEAR_RATIO = 0.75
SUSPECT_LOW_RATIO = 0.6
MIN_OWN_BASELINE_DAYS = 7
OWN_BASELINE_LOOKBACK_DAYS = 28
LAPSE_DAYS = 3
KCAL_PER_KG = 7_700
TARGET_MARGIN_KCAL = 150
CALIBRATION_MIN_PAIRED = 21
CALIBRATION_MIN_WEIGHINS = 10
CALIBRATION_ALPHA = 0.90
RECENT_WEIGHT_DAYS = 7
WEIGHT_MODE_TARGETS: dict[str, tuple[int, int]] = {
    "維持": (0, 0),
    "絞る": (-350, -250),
}

# Intake statuses whose kcal can enter the window mean.
USABLE_INTAKE: frozenset[str] = frozenset({"settled", "provisional"})
# Intake statuses that mean "food was logged" (non-zero intake).
LOGGED_INTAKE: frozenset[str] = frozenset(
    {"settled", "provisional", "suspect_low", "athlete_reported_incomplete"}
)
# Intake statuses of a closed day with no food logged.
UNLOGGED_CLOSED: frozenset[str] = frozenset({"pending", "not_logged"})

CALIBRATION_NOTES: tuple[str, ...] = (
    "Early deficits are overstated by the scale: glycogen and the water bound "
    "to it drop first, so the first days of a deficit lose more weight than "
    "the energy gap explains.",
    "The weight slope covers every day of the calibration window, while the "
    "logged mean covers only the paired days (settled/provisional intake with "
    "full-wear expenditure).",
)


@dataclass(frozen=True)
class EnergyDay:
    """One ``daily_energy`` row plus the day's summed activity time."""

    date: date
    consumed_kcal: int | None
    includes_consumed: bool | None
    total_kcal: int | None
    bmr_kcal: int | None
    coverage_seconds: int | None
    awake_seconds: int | None
    asleep_seconds: int | None
    activity_seconds: int
    fetched_at: datetime | None
    consumed_changed_at: datetime | None


@dataclass(frozen=True)
class Confirmation:
    """The athlete's own statement about one day's intake log."""

    status: Literal["complete", "incomplete"]
    confirmed_at: datetime
    note: str | None


# ----------------------------------------------------------------------------
# Day-level helpers
# ----------------------------------------------------------------------------


def _day_over(day: EnergyDay, as_of: date) -> bool:
    """A day is over once ``as_of`` is past it or its summary covers 24 h."""
    return day.date < as_of or (day.coverage_seconds or 0) >= FULL_DAY_SECONDS


def is_settled(day: EnergyDay) -> bool:
    """True once the latest fetch happened ``SETTLE_DAYS`` after the day began."""
    if day.fetched_at is None:
        return False
    settle_at = datetime.combine(day.date, datetime.min.time()) + timedelta(
        days=SETTLE_DAYS
    )
    return day.fetched_at >= settle_at


def _intake_value(day: EnergyDay) -> int | None:
    """The day's intake, or ``None`` when nothing was logged (0 / null)."""
    if day.includes_consumed is False:
        return None
    if day.consumed_kcal is None or day.consumed_kcal <= 0:
        return None
    return day.consumed_kcal


def confirmation_applies(day: EnergyDay | None, conf: Confirmation | None) -> bool:
    """A confirmation counts unless the intake changed after it was given."""
    if conf is None:
        return False
    return not (
        day is not None
        and day.consumed_changed_at is not None
        and day.consumed_changed_at > conf.confirmed_at
    )


def classify_intake(
    day: EnergyDay | None,
    *,
    as_of: date,
    own_median_kcal: float | None,
    confirmation: Confirmation | None,
) -> IntakeStatus:
    """Classify one day's intake (see the module docstring for the order)."""
    if day is None:
        return "no_data"
    if not _day_over(day, as_of):
        return "in_progress"

    settled = is_settled(day)
    intake = _intake_value(day)
    if intake is None:
        return "not_logged" if settled else "pending"

    conf = confirmation if confirmation_applies(day, confirmation) else None
    if conf is not None and conf.status == "incomplete":
        return "athlete_reported_incomplete"

    if own_median_kcal is not None:
        floor: float | None = SUSPECT_LOW_RATIO * own_median_kcal
    elif day.bmr_kcal is not None:
        floor = SUSPECT_LOW_RATIO * day.bmr_kcal
    else:
        floor = None
    confirmed_complete = conf is not None and conf.status == "complete"
    if floor is not None and intake < floor and not confirmed_complete:
        return "suspect_low"

    return "settled" if settled else "provisional"


def classify_expenditure(day: EnergyDay | None, *, as_of: date) -> ExpenditureStatus:
    """Classify one day's expenditure (coverage and wear time)."""
    if day is None or day.total_kcal is None:
        return "no_data"
    if not _day_over(day, as_of):
        return "in_progress"
    coverage = day.coverage_seconds or 0
    if coverage < FULL_DAY_SECONDS:
        return "unsynced"
    worn = (day.awake_seconds or 0) + (day.asleep_seconds or 0) + day.activity_seconds
    if worn / coverage < MIN_WEAR_RATIO:
        return "low_wear"
    return "ok"


def own_median_intake(
    days_by_date: dict[date, EnergyDay], target: date
) -> float | None:
    """Median intake of settled logged days in the 28 days before ``target``.

    Returns ``None`` when fewer than ``MIN_OWN_BASELINE_DAYS`` such days exist
    (the caller then falls back to the BMR floor).
    """
    values: list[int] = []
    for offset in range(1, OWN_BASELINE_LOOKBACK_DAYS + 1):
        day = days_by_date.get(target - timedelta(days=offset))
        if day is None or not is_settled(day):
            continue
        intake = _intake_value(day)
        if intake is not None:
            values.append(intake)
    if len(values) < MIN_OWN_BASELINE_DAYS:
        return None
    return float(statistics.median(values))


def _confirmation_dict(
    day: EnergyDay | None, conf: Confirmation | None
) -> dict[str, Any] | None:
    if conf is None:
        return None
    return {
        "status": conf.status,
        "note": conf.note,
        "confirmed_at": conf.confirmed_at.isoformat(),
        "ignored": not confirmation_applies(day, conf),
    }


def day_record(
    target: date,
    day: EnergyDay | None,
    *,
    as_of: date,
    own_median_kcal: float | None,
    confirmation: Confirmation | None,
) -> dict[str, Any]:
    """Build the per-day output dict (statuses, kcal and ``used``)."""
    intake_status = classify_intake(
        day, as_of=as_of, own_median_kcal=own_median_kcal, confirmation=confirmation
    )
    expenditure_status = classify_expenditure(day, as_of=as_of)
    intake = _intake_value(day) if day is not None else None
    expenditure = day.total_kcal if day is not None else None
    balance = (
        intake - expenditure if intake is not None and expenditure is not None else None
    )
    used = intake_status in USABLE_INTAKE and expenditure_status == "ok"
    return {
        "date": target.isoformat(),
        "intake_kcal": intake,
        "expenditure_kcal": expenditure,
        "balance_kcal": balance,
        "intake_status": intake_status,
        "expenditure_status": expenditure_status,
        "used": used,
        "confirmation": _confirmation_dict(day, confirmation),
    }


def _exclusion_reason(day: dict[str, Any]) -> str:
    """Why a day is out of the mean: the intake status first, else expenditure."""
    if day["intake_status"] not in USABLE_INTAKE:
        return str(day["intake_status"])
    return str(day["expenditure_status"])


# ----------------------------------------------------------------------------
# Window / logging / target / calibration
# ----------------------------------------------------------------------------


def required_days(window_days: int) -> int:
    """Minimum usable days for a window: five of every seven."""
    return math.ceil(window_days * 5 / 7)


def _mean(values: list[int]) -> int | None:
    return round(statistics.fmean(values)) if values else None


def summarize_window(days: list[dict[str, Any]], *, window_days: int) -> dict[str, Any]:
    """Average only the usable days of the window; list every excluded date.

    Missing days are never imputed: the mean is over the used days alone.
    """
    used = [d for d in days if d["used"]]
    need = required_days(window_days)
    any_logged = any(d["intake_status"] in LOGGED_INTAKE for d in days)
    if not any_logged:
        status = "no_logging"
    elif len(used) >= need:
        status = "ok"
    else:
        status = "insufficient"
    return {
        "status": status,
        "paired_days": len(used),
        "required_days": need,
        "mean_intake_kcal": _mean([d["intake_kcal"] for d in used]),
        "mean_expenditure_kcal": _mean([d["expenditure_kcal"] for d in used]),
        "mean_balance_kcal": _mean([d["balance_kcal"] for d in used]),
        "provisional_days": sum(1 for d in used if d["intake_status"] == "provisional"),
        "excluded": [
            {"date": d["date"], "reason": _exclusion_reason(d)}
            for d in days
            if not d["used"]
        ],
    }


def logging_state(days: list[dict[str, Any]], *, as_of: date) -> dict[str, Any]:
    """First / last logged day and whether logging has lapsed.

    ``days_since_last_log`` counts the closed days after the last logged day
    (as_of itself is still open). ``lapsed`` is true when the trailing
    ``LAPSE_DAYS`` or more closed days all have no intake (pending/not_logged).
    """
    ordered = sorted(days, key=lambda d: d["date"])
    logged = [d["date"] for d in ordered if d["intake_status"] in LOGGED_INTAKE]
    first = logged[0] if logged else None
    last = logged[-1] if logged else None
    days_since: int | None = None
    if last is not None:
        days_since = max((as_of - date.fromisoformat(last)).days - 1, 0)

    streak = 0
    for d in reversed(ordered):
        closed = date.fromisoformat(d["date"]) < as_of
        if not closed or d["intake_status"] == "in_progress":
            continue
        if d["intake_status"] in UNLOGGED_CLOSED:
            streak += 1
        else:
            break
    return {
        "first_logged_date": first,
        "last_logged_date": last,
        "days_since_last_log": days_since,
        "lapsed": streak >= LAPSE_DAYS,
    }


def compare_to_weight_mode(
    mean_balance_kcal: float | None, weight_mode: str | None
) -> dict[str, Any]:
    """Compare the logged mean balance against the block's weight_mode band."""
    target = WEIGHT_MODE_TARGETS.get(weight_mode) if weight_mode else None
    band: list[int] | None = None
    if target is not None:
        band = [target[0] - TARGET_MARGIN_KCAL, target[1] + TARGET_MARGIN_KCAL]
    result: dict[str, Any] = {
        "weight_mode": weight_mode,
        "band_kcal": band,
        "verdict": None,
        "reason": None,
        "basis": "logged",
    }
    if band is None:
        result["reason"] = "unknown_weight_mode"
    elif mean_balance_kcal is None:
        result["reason"] = "no_mean"
    elif mean_balance_kcal < band[0]:
        result["verdict"] = "deeper_than_target"
    elif mean_balance_kcal > band[1]:
        result["verdict"] = "shallower_than_target"
    else:
        result["verdict"] = "within_target"
    return result


def calibrate_against_weight(
    days: list[dict[str, Any]], weigh_ins: list[tuple[date, float]]
) -> dict[str, Any]:
    """Check the logged mean against the weight trend (Theil-Sen, 90% CI).

    Values are reported, never corrected.
    """
    used = [d for d in days if d["used"]]
    logged_mean = _mean([d["balance_kcal"] for d in used])
    result: dict[str, Any] = {
        "status": "insufficient",
        "reason": None,
        "paired_days": len(used),
        "n_weighins": len(weigh_ins),
        "logged_mean_kcal": logged_mean,
        "implied_mean_kcal": None,
        "implied_ci_kcal": None,
        "notes": list(CALIBRATION_NOTES),
    }
    if len(used) < CALIBRATION_MIN_PAIRED:
        result["reason"] = "too_few_paired_days"
        return result
    if len(weigh_ins) < CALIBRATION_MIN_WEIGHINS:
        result["reason"] = "too_few_weighins"
        return result

    from scipy.stats import theilslopes

    origin = min(d for d, _ in weigh_ins)
    xs = [float((d - origin).days) for d, _ in weigh_ins]
    ys = [float(w) for _, w in weigh_ins]
    slope, _intercept, low, high = theilslopes(ys, xs, alpha=CALIBRATION_ALPHA)
    implied = float(slope) * KCAL_PER_KG
    # Judge against the rounded (reported) bounds so the verdict agrees with
    # the numbers shown and float noise on a tight CI cannot flip it.
    ci_lo, ci_hi = sorted(
        (round(float(low) * KCAL_PER_KG), round(float(high) * KCAL_PER_KG))
    )
    result["implied_mean_kcal"] = round(implied)
    result["implied_ci_kcal"] = [ci_lo, ci_hi]

    if logged_mean is None:  # unreachable: used is non-empty here
        return result
    if ci_lo <= logged_mean <= ci_hi:
        result["status"] = "consistent"
    elif logged_mean < ci_lo:
        result["status"] = "logged_deficit_exceeds_weight"
    else:
        result["status"] = "logged_deficit_below_weight"
    return result


def weight_summary(
    weigh_ins: list[tuple[date, float]], *, end_date: date
) -> dict[str, Any]:
    """Recent median weight (last 7 days), weigh-in count and weekly slope."""
    recent_start = end_date - timedelta(days=RECENT_WEIGHT_DAYS - 1)
    recent = [w for d, w in weigh_ins if recent_start <= d <= end_date]
    slope_week: float | None = None
    if len({d for d, _ in weigh_ins}) >= 2:
        from scipy.stats import theilslopes

        origin = min(d for d, _ in weigh_ins)
        xs = [float((d - origin).days) for d, _ in weigh_ins]
        ys = [float(w) for _, w in weigh_ins]
        slope = theilslopes(ys, xs, alpha=CALIBRATION_ALPHA)[0]
        slope_week = round(float(slope) * 7, 3)
    return {
        "recent_median_kg": (
            round(float(statistics.median(recent)), 2) if recent else None
        ),
        "n_weighins": len(weigh_ins),
        "slope_kg_per_week": slope_week,
    }


def build_energy_balance(
    days: list[EnergyDay],
    confirmations: dict[date, Confirmation],
    weigh_ins: list[tuple[date, float]],
    weight_mode: str | None,
    *,
    end_date: date,
    window_days: int,
    calibration_days: int,
    as_of: date,
) -> dict[str, Any]:
    """Assemble the full energy-balance payload from stored facts.

    ``days`` may hold the athlete's whole history up to ``as_of`` (the own
    baseline and the logging state look back beyond the window). ``days`` in
    the output cover the window plus -- when ``as_of`` is no more than
    ``window_days`` past ``end_date`` -- the days after it up to ``as_of``
    (flagged ``in_window: False`` and never used). The target's ``block_id`` /
    ``crosses_block_boundary`` are filled in by the reader.
    """
    by_date = {d.date: d for d in days}
    window_start = end_date - timedelta(days=window_days - 1)
    cal_start = end_date - timedelta(days=calibration_days - 1)
    history_start = min([window_start, cal_start, *by_date.keys()])
    last_day = max(end_date, as_of)

    records: dict[date, dict[str, Any]] = {}
    cursor = history_start
    while cursor <= last_day:
        day = by_date.get(cursor)
        records[cursor] = day_record(
            cursor,
            day,
            as_of=as_of,
            own_median_kcal=own_median_intake(by_date, cursor),
            confirmation=confirmations.get(cursor),
        )
        cursor += timedelta(days=1)

    def _span(start: date, end: date) -> list[dict[str, Any]]:
        return [records[d] for d in sorted(records) if start <= d <= end]

    window_records = _span(window_start, end_date)
    trailing_end = min(as_of, end_date + timedelta(days=window_days))
    trailing = _span(end_date + timedelta(days=1), trailing_end)
    out_days = [{**r, "in_window": True} for r in window_records] + [
        {**r, "in_window": False, "used": False} for r in trailing
    ]

    window = summarize_window(window_records, window_days=window_days)
    logging = logging_state(_span(history_start, as_of), as_of=as_of)
    calibration = calibrate_against_weight(
        _span(cal_start, end_date),
        [(d, w) for d, w in weigh_ins if cal_start <= d <= end_date],
    )

    if window["status"] == "ok":
        target = compare_to_weight_mode(window["mean_balance_kcal"], weight_mode)
    else:
        target = compare_to_weight_mode(None, weight_mode)
        if target["reason"] != "unknown_weight_mode":
            target["reason"] = f"window_{window['status']}"
    target["calibration_status"] = calibration["status"]

    return {
        "end_date": end_date.isoformat(),
        "as_of": as_of.isoformat(),
        "window_days": window_days,
        "days": out_days,
        "window": window,
        "logging": logging,
        "target": target,
        "calibration": calibration,
        "weight": weight_summary(
            [(d, w) for d, w in weigh_ins if cal_start <= d <= end_date],
            end_date=end_date,
        ),
    }
