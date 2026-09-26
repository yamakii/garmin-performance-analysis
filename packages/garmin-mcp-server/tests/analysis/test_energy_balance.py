"""Unit tests for the energy-balance rules (issue #1434)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from garmin_mcp.analysis.energy_balance import (
    Confirmation,
    EnergyDay,
    build_energy_balance,
    calibrate_against_weight,
    classify_expenditure,
    classify_intake,
    compare_to_weight_mode,
    logging_state,
    summarize_window,
)

AS_OF = date(2026, 9, 26)
FULL = 86_400


def _day(
    d: date,
    *,
    consumed: int | None = 1800,
    total: int | None = 2300,
    bmr: int | None = 1970,
    coverage: int | None = FULL,
    awake: int | None = 55_000,
    asleep: int | None = 28_000,
    activity: int = 0,
    fetched_at: datetime | None = None,
    changed_at: datetime | None = None,
) -> EnergyDay:
    """An EnergyDay; fetched the next morning unless given."""
    if fetched_at is None:
        fetched_at = datetime.combine(d + timedelta(days=1), datetime.min.time())
        fetched_at += timedelta(hours=6)
    return EnergyDay(
        date=d,
        consumed_kcal=consumed,
        includes_consumed=consumed is not None,
        total_kcal=total,
        bmr_kcal=bmr,
        coverage_seconds=coverage,
        awake_seconds=awake,
        asleep_seconds=asleep,
        activity_seconds=activity,
        fetched_at=fetched_at,
        consumed_changed_at=changed_at,
    )


def _settled_fetch(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=8), datetime.min.time())


def _record(
    d: date,
    *,
    intake: int | None,
    expenditure: int | None,
    intake_status: str,
    expenditure_status: str = "ok",
) -> dict[str, Any]:
    used = intake_status in ("settled", "provisional") and expenditure_status == "ok"
    return {
        "date": d.isoformat(),
        "intake_kcal": intake,
        "expenditure_kcal": expenditure,
        "balance_kcal": (
            intake - expenditure
            if intake is not None and expenditure is not None
            else None
        ),
        "intake_status": intake_status,
        "expenditure_status": expenditure_status,
        "used": used,
        "confirmation": None,
    }


def _run(days: list[EnergyDay], **kwargs: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "end_date": AS_OF - timedelta(days=1),
        "window_days": 7,
        "calibration_days": 28,
        "as_of": AS_OF,
    }
    params.update(kwargs)
    confirmations = params.pop("confirmations", {})
    weigh_ins = params.pop("weigh_ins", [])
    weight_mode = params.pop("weight_mode", "維持")
    result: dict[str, Any] = build_energy_balance(
        days,
        confirmations,
        weigh_ins,
        weight_mode,
        end_date=params["end_date"],
        window_days=params["window_days"],
        calibration_days=params["calibration_days"],
        as_of=params["as_of"],
    )
    return result


def _by_date(result: dict[str, Any], d: date) -> dict[str, Any]:
    days: list[dict[str, Any]] = result["days"]
    return next(x for x in days if x["date"] == d.isoformat())


@pytest.mark.unit
def test_in_progress_when_day_not_over() -> None:
    today = _day(AS_OF, consumed=909, total=851, coverage=37_260)

    assert (
        classify_intake(today, as_of=AS_OF, own_median_kcal=None, confirmation=None)
        == "in_progress"
    )
    assert classify_expenditure(today, as_of=AS_OF) == "in_progress"

    result = _run([today])
    row = _by_date(result, AS_OF)
    assert row["intake_status"] == "in_progress"
    assert row["expenditure_status"] == "in_progress"
    assert row["used"] is False
    assert row["in_window"] is False


@pytest.mark.unit
def test_pending_zero_before_settle() -> None:
    d = date(2026, 9, 24)
    day = _day(d, consumed=0, fetched_at=datetime(2026, 9, 25, 7, 0))
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=None)
        == "pending"
    )


@pytest.mark.unit
def test_not_logged_only_after_settle() -> None:
    d = date(2026, 9, 10)
    day = _day(d, consumed=None, fetched_at=_settled_fetch(d))
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=None)
        == "not_logged"
    )

    result = _run([day], end_date=d, as_of=d + timedelta(days=9))
    assert {"date": d.isoformat(), "reason": "not_logged"} in result["window"][
        "excluded"
    ]


@pytest.mark.unit
def test_suspect_low_vs_own_median() -> None:
    target = date(2026, 9, 20)
    intakes = [1500, 1600, 1700, 1777, 1777, 1800, 1900, 2000]
    history = [
        _day(
            target - timedelta(days=10 + i),
            consumed=kcal,
            fetched_at=_settled_fetch(target - timedelta(days=10 + i)),
        )
        for i, kcal in enumerate(intakes)
    ]

    low = _run([*history, _day(target, consumed=900)], end_date=target)
    assert _by_date(low, target)["intake_status"] == "suspect_low"

    normal = _run([*history, _day(target, consumed=1405)], end_date=target)
    assert _by_date(normal, target)["intake_status"] == "provisional"

    day = _day(target, consumed=1405, fetched_at=_settled_fetch(target))
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=1777.0, confirmation=None)
        == "settled"
    )
    low_day = _day(target, consumed=900, fetched_at=_settled_fetch(target))
    assert (
        classify_intake(low_day, as_of=AS_OF, own_median_kcal=1777.0, confirmation=None)
        == "suspect_low"
    )


@pytest.mark.unit
def test_suspect_low_fallback_bmr() -> None:
    target = date(2026, 9, 20)
    history = [
        _day(
            target - timedelta(days=10 + i),
            consumed=2500,
            fetched_at=_settled_fetch(target - timedelta(days=10 + i)),
        )
        for i in range(3)
    ]
    result = _run([*history, _day(target, consumed=1100, bmr=1973)], end_date=target)
    assert _by_date(result, target)["intake_status"] == "suspect_low"

    ok = _run([*history, _day(target, consumed=1200, bmr=1973)], end_date=target)
    assert _by_date(ok, target)["intake_status"] == "provisional"


@pytest.mark.unit
def test_complete_confirmation_overrides_suspect_low() -> None:
    d = date(2026, 9, 20)
    day = _day(d, consumed=900, bmr=1973)
    conf = Confirmation(
        status="complete", confirmed_at=datetime(2026, 9, 22, 9, 0), note=None
    )
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=None)
        == "suspect_low"
    )
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=conf)
        == "provisional"
    )

    result = _run([day], end_date=d, confirmations={d: conf})
    row = _by_date(result, d)
    assert row["used"] is True
    assert row["confirmation"]["status"] == "complete"
    assert row["confirmation"]["ignored"] is False


@pytest.mark.unit
def test_incomplete_confirmation_excludes_day() -> None:
    d = date(2026, 9, 10)
    day = _day(d, consumed=1800, fetched_at=_settled_fetch(d))
    conf = Confirmation(
        status="incomplete", confirmed_at=datetime(2026, 9, 11, 9, 0), note="外食"
    )
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=conf)
        == "athlete_reported_incomplete"
    )

    result = _run([day], end_date=d, as_of=AS_OF, confirmations={d: conf})
    assert _by_date(result, d)["used"] is False
    assert {
        "date": d.isoformat(),
        "reason": "athlete_reported_incomplete",
    } in result[
        "window"
    ]["excluded"]


@pytest.mark.unit
def test_confirmation_ignored_after_later_edit() -> None:
    d = date(2026, 9, 20)
    day = _day(d, consumed=1800, changed_at=datetime(2026, 9, 23, 8, 0))
    conf = Confirmation(
        status="incomplete", confirmed_at=datetime(2026, 9, 21, 9, 0), note=None
    )
    assert (
        classify_intake(day, as_of=AS_OF, own_median_kcal=None, confirmation=conf)
        == "provisional"
    )
    result = _run([day], end_date=d, confirmations={d: conf})
    assert _by_date(result, d)["confirmation"]["ignored"] is True


@pytest.mark.unit
def test_expenditure_unsynced_on_closed_day() -> None:
    day = _day(date(2026, 9, 20), coverage=50_000)
    assert classify_expenditure(day, as_of=AS_OF) == "unsynced"


@pytest.mark.unit
def test_low_wear_counts_activity_time() -> None:
    worn = int(0.70 * FULL)
    d = date(2026, 9, 20)
    with_run = _day(d, awake=worn - 28_000, asleep=28_000, activity=6 * 3600)
    without = _day(d, awake=worn - 28_000, asleep=28_000, activity=0)
    assert classify_expenditure(with_run, as_of=AS_OF) == "ok"
    assert classify_expenditure(without, as_of=AS_OF) == "low_wear"


@pytest.mark.unit
def test_window_required_days_scales() -> None:
    start = date(2026, 9, 19)
    records = [
        _record(
            start + timedelta(days=i),
            intake=1800,
            expenditure=2300,
            intake_status="provisional" if i < 4 else "not_logged",
        )
        for i in range(7)
    ]
    week = summarize_window(records, window_days=7)
    assert week["status"] == "insufficient"
    assert week["required_days"] == 5
    assert week["paired_days"] == 4

    two_weeks = summarize_window(records, window_days=14)
    assert two_weeks["required_days"] == 10


@pytest.mark.unit
def test_window_never_imputes_missing_days() -> None:
    start = date(2026, 9, 19)
    records = [
        _record(
            start + timedelta(days=i),
            intake=1800,
            expenditure=2300,
            intake_status="settled",
        )
        for i in range(5)
    ] + [
        _record(
            start + timedelta(days=5 + i),
            intake=None,
            expenditure=2300,
            intake_status="not_logged",
        )
        for i in range(2)
    ]
    window = summarize_window(records, window_days=7)
    assert window["status"] == "ok"
    assert window["mean_balance_kcal"] == -500
    assert window["paired_days"] == 5
    assert len(window["excluded"]) == 2
    assert {e["reason"] for e in window["excluded"]} == {"not_logged"}


@pytest.mark.unit
def test_window_no_logging() -> None:
    start = date(2026, 9, 19)
    records = [
        _record(
            start + timedelta(days=i),
            intake=None,
            expenditure=2300 if i % 2 else None,
            intake_status="not_logged" if i % 2 else "no_data",
            expenditure_status="ok" if i % 2 else "no_data",
        )
        for i in range(7)
    ]
    window = summarize_window(records, window_days=7)
    assert window["status"] == "no_logging"
    assert window["mean_balance_kcal"] is None


@pytest.mark.unit
def test_logging_lapsed_after_three_closed_days() -> None:
    records = [
        _record(
            date(2026, 9, 21),
            intake=1800,
            expenditure=2300,
            intake_status="provisional",
        ),
        _record(
            date(2026, 9, 22),
            intake=1800,
            expenditure=2300,
            intake_status="provisional",
        ),
        _record(
            date(2026, 9, 23), intake=None, expenditure=2300, intake_status="pending"
        ),
        _record(
            date(2026, 9, 24), intake=None, expenditure=2300, intake_status="pending"
        ),
        _record(
            date(2026, 9, 25), intake=None, expenditure=2300, intake_status="pending"
        ),
        _record(
            date(2026, 9, 26),
            intake=None,
            expenditure=851,
            intake_status="in_progress",
            expenditure_status="in_progress",
        ),
    ]
    state = logging_state(records, as_of=AS_OF)
    assert state["lapsed"] is True
    assert state["days_since_last_log"] == 3
    assert state["last_logged_date"] == "2026-09-22"
    assert state["first_logged_date"] == "2026-09-21"

    not_lapsed = logging_state(records[:4], as_of=date(2026, 9, 25))
    assert not_lapsed["lapsed"] is False


@pytest.mark.unit
def test_weight_mode_verdicts() -> None:
    assert compare_to_weight_mode(-469, "維持")["verdict"] == "deeper_than_target"
    assert compare_to_weight_mode(-300, "絞る")["verdict"] == "within_target"
    assert compare_to_weight_mode(-80, "絞る")["verdict"] == "shallower_than_target"
    unknown = compare_to_weight_mode(-300, "不明")
    assert unknown["verdict"] is None
    assert unknown["reason"] == "unknown_weight_mode"
    assert compare_to_weight_mode(-300, "絞る")["basis"] == "logged"
    assert compare_to_weight_mode(0, "維持")["band_kcal"] == [-150, 150]


def _cal_records(n: int, balance: int) -> list[dict[str, Any]]:
    start = date(2026, 8, 29)
    return [
        _record(
            start + timedelta(days=i),
            intake=2000 + balance,
            expenditure=2000,
            intake_status="settled",
        )
        for i in range(n)
    ]


@pytest.mark.unit
def test_calibration_insufficient_short_history() -> None:
    weigh_ins = [(date(2026, 8, 29) + timedelta(days=i), 78.0) for i in range(28)]
    result = calibrate_against_weight(_cal_records(9, -300), weigh_ins)
    assert result["status"] == "insufficient"
    assert result["reason"] == "too_few_paired_days"
    assert result["paired_days"] == 9

    few = calibrate_against_weight(_cal_records(28, -300), weigh_ins[:5])
    assert few["reason"] == "too_few_weighins"


@pytest.mark.unit
def test_calibration_flags_underlogging() -> None:
    start = date(2026, 8, 29)
    pattern = (0.3, -0.3, 0.0, 0.3)
    weigh_ins = [
        (start + timedelta(days=t), 78.0 - 0.02 * t + pattern[t % len(pattern)])
        for t in range(28)
    ]
    result = calibrate_against_weight(_cal_records(28, -560), weigh_ins)
    assert result["status"] == "logged_deficit_exceeds_weight"
    lo, hi = result["implied_ci_kcal"]
    assert lo <= result["implied_mean_kcal"] <= hi
    assert result["logged_mean_kcal"] == -560
    assert len(result["notes"]) == 2


@pytest.mark.unit
def test_calibration_consistent() -> None:
    start = date(2026, 8, 29)
    per_day = -300 / 7_700
    pattern = (0.1, -0.1, 0.0, 0.05, -0.15, 0.1, -0.05)
    weigh_ins = [
        (start + timedelta(days=t), 78.0 + per_day * t + pattern[t % len(pattern)])
        for t in range(28)
    ]
    result = calibrate_against_weight(_cal_records(28, -300), weigh_ins)
    assert result["status"] == "consistent"
    assert result["reason"] is None
