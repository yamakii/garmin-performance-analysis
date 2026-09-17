"""Next-morning recovery cost of a long run (pure functions, no I/O).

A long run always costs something the next morning; the question is whether it
cost *more than this athlete's own normal*. This module ties one run to the
``daily_wellness`` rows of the following two mornings and judges three
deterministic criteria against a trailing personal baseline (#1218):

- ``rhr_two_day`` -- resting HR at least ``RHR_DELTA_TRIGGER_BPM`` above the
  baseline median on **both** d+1 and d+2. A single elevated morning is normal
  after any long run (2026-07-18 read +0 / +4 and must not fire), so the
  criterion needs the bump to persist. When the d+2 row is missing the
  criterion falls back to d+1 alone, but only at the stricter
  ``RHR_SINGLE_MORNING_TRIGGER_BPM``.
- ``readiness`` -- d+1 Training Readiness below ``READINESS_TRIGGER``.
- ``hrv`` -- d+1 overnight HRV at or below ``HRV_DELTA_TRIGGER_PCT`` relative to
  the baseline median.

``cost_flag`` requires ``MIN_CRITERIA_TO_FIRE`` of the three: one lone marker is
day-to-day noise (2026-06-28 read HRV -23 % with everything else normal and was
followed by a clean week). On the backtest (all runs >= 12 km with wellness
coverage, n=18) the two-of-three rule fires on exactly the two 2026
injury-trigger events (2025-12-14 half, 2025-12-29 28.6 km) and on none of the
nine 2026 ladder long runs.

The baseline is a trailing **median** over ``BASELINE_WINDOW_DAYS`` days ending
the day before the run (the run day itself is excluded, since its own evening
already carries the load). The median rather than the mean keeps one bad night
from moving the reference. Everything is null-safe: device-off days are skipped,
and a baseline built from fewer than ``MIN_BASELINE_SAMPLES`` resting-HR samples
-- or a missing d+1 row -- reports ``insufficient_data`` instead of guessing.

This module only describes the cost; deciding what to do about it (cut back,
delay the next quality session) belongs to the gate / weekly review above it.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

#: Resting-HR rise (bpm) over baseline that counts as an elevated morning.
RHR_DELTA_TRIGGER_BPM = 2.0

#: Stricter single-morning resting-HR rise used when the d+2 row is missing.
RHR_SINGLE_MORNING_TRIGGER_BPM = 3.0

#: Training Readiness below this on d+1 counts as an expensive night.
READINESS_TRIGGER = 35

#: Overnight HRV change (%) vs baseline that counts as an expensive night.
HRV_DELTA_TRIGGER_PCT = -15.0

#: Trailing window (days) for the personal baseline, run day excluded.
BASELINE_WINDOW_DAYS = 14

#: Criteria that must fire before the run is flagged as costly.
MIN_CRITERIA_TO_FIRE = 2

#: Minimum non-null resting-HR samples before the baseline is trustworthy.
MIN_BASELINE_SAMPLES = 5

#: Criterion order, used for the returned list and for ``reason_ja``.
_CRITERIA_ORDER = ("rhr_two_day", "readiness", "hrv")


def compute_long_run_recovery_cost(
    run: dict[str, Any],
    wellness_d1: dict[str, Any] | None,
    wellness_d2: dict[str, Any] | None,
    baseline_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Judge the next-morning recovery cost of one run.

    Args:
        run: The run being judged -- ``activity_id``, ``activity_date``,
            ``distance_km``, and optionally ``avg_heart_rate`` /
            ``temperature_c`` (carried through for context).
        wellness_d1: ``daily_wellness`` row for ``activity_date + 1`` (reads
            ``resting_hr``, ``hrv_overnight_ms``, ``training_readiness``,
            ``sleep_seconds``, ``body_battery_low``), or ``None`` when the
            morning was not recorded.
        wellness_d2: ``daily_wellness`` row for ``activity_date + 2``, or
            ``None``.
        baseline_rows: ``daily_wellness`` rows in
            ``[activity_date - BASELINE_WINDOW_DAYS, activity_date - 1]``.
            Null values are skipped per metric.

    Returns:
        ``{activity_id, activity_date, distance_km, avg_heart_rate,
        temperature_c, baseline: {rhr_median, hrv_median, n}, d1: {...}|None,
        d2: {...}|None, criteria: [{name, fired, value, threshold}],
        criteria_fired: int, cost_flag: bool, insufficient_data: bool,
        reason_ja: str}``.

        ``cost_flag`` is ``True`` only when at least
        ``MIN_CRITERIA_TO_FIRE`` criteria fired *and* the read is trustworthy;
        ``insufficient_data`` (short baseline or missing d+1) forces it to
        ``False`` rather than reporting a verdict built on nothing.
    """
    rhr_samples = _values(baseline_rows, "resting_hr")
    hrv_samples = _values(baseline_rows, "hrv_overnight_ms")
    rhr_median = _median(rhr_samples)
    hrv_median = _median(hrv_samples)

    d1 = _d1_block(wellness_d1, rhr_median, hrv_median)
    d2 = _d2_block(wellness_d2, rhr_median)

    insufficient_data = len(rhr_samples) < MIN_BASELINE_SAMPLES or d1 is None

    criteria = _criteria(d1, d2)
    criteria_fired = sum(1 for c in criteria if c["fired"])
    cost_flag = not insufficient_data and criteria_fired >= MIN_CRITERIA_TO_FIRE

    return {
        "activity_id": run.get("activity_id"),
        "activity_date": _as_str(run.get("activity_date")),
        "distance_km": _as_float(run.get("distance_km")),
        "avg_heart_rate": run.get("avg_heart_rate"),
        "temperature_c": _as_float(run.get("temperature_c")),
        "baseline": {
            "rhr_median": rhr_median,
            "hrv_median": hrv_median,
            "n": len(rhr_samples),
        },
        "d1": d1,
        "d2": d2,
        "criteria": criteria,
        "criteria_fired": criteria_fired,
        "cost_flag": cost_flag,
        "insufficient_data": insufficient_data,
        "reason_ja": _reason_ja(
            d1, d2, criteria_fired, cost_flag, insufficient_data, len(rhr_samples)
        ),
    }


def _d1_block(
    row: dict[str, Any] | None, rhr_median: float | None, hrv_median: float | None
) -> dict[str, Any] | None:
    """The d+1 morning as deltas against the baseline (``None`` when absent)."""
    if row is None:
        return None

    rhr = _as_float(row.get("resting_hr"))
    hrv = _as_float(row.get("hrv_overnight_ms"))
    sleep_seconds = _as_float(row.get("sleep_seconds"))

    hrv_delta_pct = None
    if hrv is not None and hrv_median:
        hrv_delta_pct = round((hrv - hrv_median) / hrv_median * 100, 1)

    return {
        "date": _as_str(row.get("date")),
        "rhr": rhr,
        "rhr_delta": _delta(rhr, rhr_median),
        "hrv": hrv,
        "hrv_delta_pct": hrv_delta_pct,
        "readiness": row.get("training_readiness"),
        "sleep_hours": (
            None if sleep_seconds is None else round(sleep_seconds / 3600, 1)
        ),
        "body_battery_low": row.get("body_battery_low"),
    }


def _d2_block(
    row: dict[str, Any] | None, rhr_median: float | None
) -> dict[str, Any] | None:
    """The d+2 morning's resting HR and its delta (``None`` when absent)."""
    if row is None:
        return None
    rhr = _as_float(row.get("resting_hr"))
    return {
        "date": _as_str(row.get("date")),
        "rhr": rhr,
        "rhr_delta": _delta(rhr, rhr_median),
    }


def _criteria(
    d1: dict[str, Any] | None, d2: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Evaluate the three criteria in reporting order."""
    d1 = d1 or {}
    rhr_d1 = d1.get("rhr_delta")
    rhr_d2 = (d2 or {}).get("rhr_delta")
    readiness = d1.get("readiness")
    hrv_delta_pct = d1.get("hrv_delta_pct")

    return [
        {
            "name": "rhr_two_day",
            "fired": _rhr_two_day_fired(rhr_d1, rhr_d2),
            "value": _rhr_value(rhr_d1, rhr_d2),
            "threshold": (
                RHR_DELTA_TRIGGER_BPM
                if rhr_d2 is not None
                else RHR_SINGLE_MORNING_TRIGGER_BPM
            ),
        },
        {
            "name": "readiness",
            "fired": readiness is not None and readiness < READINESS_TRIGGER,
            "value": readiness,
            "threshold": READINESS_TRIGGER,
        },
        {
            "name": "hrv",
            "fired": hrv_delta_pct is not None
            and hrv_delta_pct <= HRV_DELTA_TRIGGER_PCT,
            "value": hrv_delta_pct,
            "threshold": HRV_DELTA_TRIGGER_PCT,
        },
    ]


def _rhr_two_day_fired(rhr_d1: float | None, rhr_d2: float | None) -> bool:
    """Whether resting HR stayed elevated across the two mornings.

    Both mornings must clear ``RHR_DELTA_TRIGGER_BPM``. With no d+2 row the
    criterion still fires on d+1 alone, but only at the stricter
    ``RHR_SINGLE_MORNING_TRIGGER_BPM``, since one morning cannot show
    persistence.
    """
    if rhr_d1 is None:
        return False
    if rhr_d2 is None:
        return rhr_d1 >= RHR_SINGLE_MORNING_TRIGGER_BPM
    return rhr_d1 >= RHR_DELTA_TRIGGER_BPM and rhr_d2 >= RHR_DELTA_TRIGGER_BPM


def _rhr_value(rhr_d1: float | None, rhr_d2: float | None) -> list[float | None]:
    """The criterion's reported value: both mornings' deltas."""
    return [rhr_d1, rhr_d2]


def _reason_ja(
    d1: dict[str, Any] | None,
    d2: dict[str, Any] | None,
    criteria_fired: int,
    cost_flag: bool,
    insufficient_data: bool,
    baseline_n: int,
) -> str:
    """One deterministic Japanese line describing the morning cost."""
    if d1 is None:
        return "翌朝のウェルネス記録がないため、回復コストを判定できません。"
    if insufficient_data:
        return (
            f"直前14日の安静時心拍が{baseline_n}日分しかなく、"
            "個人ベースラインを作れないため判定を保留します。"
        )

    parts = [
        f"RHR {_fmt_delta(d1.get('rhr_delta'))}/"
        f"{_fmt_delta((d2 or {}).get('rhr_delta'))}",
        f"Readiness {_fmt_value(d1.get('readiness'))}",
        f"HRV {_fmt_pct(d1.get('hrv_delta_pct'))}",
    ]
    head = "翌朝コスト" if cost_flag else "翌朝コストは通常範囲"
    body = "、".join(parts)
    return f"{head}: {body}（{criteria_fired}/{len(_CRITERIA_ORDER)} 基準）"


def _fmt_delta(value: float | None) -> str:
    """Signed baseline delta, integral values without a decimal part."""
    if value is None:
        return "欠測"
    if float(value).is_integer():
        return f"{int(value):+d}"
    return f"{value:+.1f}"


def _fmt_value(value: Any) -> str:
    """Raw value, or ``欠測`` when unmeasured."""
    return "欠測" if value is None else str(value)


def _fmt_pct(value: float | None) -> str:
    """Percentage change rounded to whole percent."""
    return "欠測" if value is None else f"{value:+.0f}%"


def _values(rows: Sequence[dict[str, Any]], column: str) -> list[float]:
    """Non-null numeric values of ``column`` across ``rows``."""
    out = []
    for row in rows:
        value = _as_float(row.get(column))
        if value is not None:
            out.append(value)
    return out


def _median(values: Sequence[float]) -> float | None:
    """Median of ``values`` rounded to 1 dp (``None`` when empty)."""
    return None if not values else round(statistics.median(values), 1)


def _delta(value: float | None, baseline: float | None) -> float | None:
    """``value - baseline`` rounded to 1 dp (``None`` when either is absent)."""
    if value is None or baseline is None:
        return None
    return round(value - baseline, 1)


def _as_float(value: Any) -> float | None:
    """Coerce to ``float``, or ``None`` when absent / non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    """Stringify a value (dates included), null-safe."""
    return None if value is None else str(value)
