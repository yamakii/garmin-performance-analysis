"""The HR ceiling on steady running, and how much of the run was judged (#1313).

Heart rate lags every change of load. After a surge, a stop or an auto-pause
the seconds until HR has settled describe the event, not the easy running the
ceiling guards, so the reader judges the ceiling through
``analysis.hr_windows.steady_mask`` and reports the share of the run it kept.
Without a time series the zone totals stand.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.analysis.run_signals import REASON_LOW_JUDGED_SHARE
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
    _seed_splits,
    _seed_zones,
)

_EASY_SPEED = 2.8
_BURST_SPEED = 4.0


def _seed_series(
    db_path: Path,
    seconds: int,
    hr: Callable[[int], float],
    speed: Callable[[int], float],
) -> None:
    """One sample per second: ``hr(t)`` and ``speed(t)``, cadence 176."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO time_series_metrics (
                activity_id, seq_no, timestamp_s, heart_rate, speed, cadence
            ) VALUES (?, ?, ?, ?, ?, 176.0)
            """,
            [(ACTIVITY_ID, t, t, hr(t), speed(t)) for t in range(seconds)],
        )
    finally:
        conn.close()


def _seed_easy_day(db_path: Path, *, avg_hr: int = 146) -> None:
    """History, today's easy run and an easy prescription with a 150 ceiling."""
    _seed_history(db_path)
    _seed_run(db_path, activity_id=ACTIVITY_ID, activity_date=TODAY, avg_hr=avg_hr)
    _seed_prescription(db_path, on_date=TODAY, hr_high=150)


def _ceiling_row(report: dict) -> dict:
    return next(c for c in report["plan"]["checks"] if c["axis"] == "hr_ceiling")


@pytest.mark.integration
def test_hr_ceiling_uses_mask_on_plain_easy_run(reader_db_path: Path) -> None:
    """A 20 s burst to 165 and its recovery are not the easy running.

    Baseline 145; the burst (600-619 s) is followed by 40 s above 150 while HR
    comes back to 146; later the athlete holds 155 for 60 s at easy pace. Only
    those 60 s are over the ceiling.
    """
    _seed_easy_day(reader_db_path)

    def hr(t: int) -> float:
        if 600 <= t < 620:
            return 165.0
        if 620 <= t < 660:
            return 164.0 - 0.35 * (t - 620)
        if 660 <= t < 780:
            return 146.0
        if 780 <= t < 840:
            return 155.0
        return 145.0

    _seed_series(
        reader_db_path,
        1200,
        hr,
        lambda t: _BURST_SPEED if 600 <= t < 620 else _EASY_SPEED,
    )

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["bpm"] == 150
    assert ceiling["seconds_over"] == 60
    assert ceiling["pct_over"] == round(60 / 1140 * 100, 1)
    assert report["judged_share"]["hr"] == pytest.approx(1140 / 1200, abs=1e-3)
    assert report["judged_share"]["form"] == pytest.approx(1180 / 1200, abs=1e-3)


@pytest.mark.integration
def test_hr_ceiling_zone_fallback_without_samples(reader_db_path: Path) -> None:
    """No time series: the zone totals and the activity's average HR stand."""
    _seed_easy_day(reader_db_path)
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 130, 300.0), (2, 130, 150, 1260.0), (3, 150, 170, 240.0)],
    )

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling == {
        "bpm": 150,
        "seconds_over": 240.0,
        "pct_over": round(240.0 / 1800.0 * 100.0, 1),
    }
    assert _ceiling_row(report)["actual"] == "146 bpm"
    assert report["judged_share"] == {"hr": None, "form": None}


@pytest.mark.integration
def test_judged_share_low_marks_form_insufficient(reader_db_path: Path) -> None:
    """600 of 1000 s standing still: form judged share 0.4, form not judged."""
    _seed_easy_day(reader_db_path)
    _seed_series(
        reader_db_path,
        1000,
        lambda _t: 140.0,
        lambda t: _EASY_SPEED if t < 400 else 0.0,
    )

    report = _report(reader_db_path)

    assert report is not None
    assert report["judged_share"]["form"] == pytest.approx(0.4)
    form = [s for s in report["signals"] if s["family"] == "form"]
    assert form
    for signal in form:
        assert signal["status"] == "insufficient", signal["metric"]
        assert signal["reason_code"] == REASON_LOW_JUDGED_SHARE
        assert "40%" in signal["reason"]
    cardio = [s for s in report["signals"] if s["family"] == "cardio"]
    assert all(s["reason_code"] != REASON_LOW_JUDGED_SHARE for s in cardio)


@pytest.mark.integration
def test_ceiling_touch_uses_masked_split_hr(reader_db_path: Path) -> None:
    """A stride and its recovery lift a kilometre to 151 bpm; steady, it is 144.

    Three 1 km laps at easy pace. In lap 2 a 20 s stride (500-519 s, 165 bpm)
    is followed by 60 s of slow jog with HR flat at 158 on its way down, then
    144. The lap table says 151 / 164 -- a ceiling touch on the averages --
    but read over its steady seconds the kilometre is 144, and no ceiling
    touch is a stride again (#1320).
    """
    _seed_easy_day(reader_db_path)
    _seed_splits(reader_db_path, ACTIVITY_ID, [(1.0, 400.0, "run")] * 3)
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.execute(
            "UPDATE splits SET heart_rate = 151, max_heart_rate = 164 "
            "WHERE activity_id = ? AND split_index = 2",
            [ACTIVITY_ID],
        )
    finally:
        conn.close()

    def hr(t: int) -> float:
        if 500 <= t < 520:
            return 165.0
        if 520 <= t < 580:
            return 157.0 if t % 2 else 159.0
        return 145.0 if t < 500 else 144.0

    def speed(t: int) -> float:
        if 500 <= t < 520:
            return 4.5
        return 1.9 if 520 <= t < 580 else 2.5

    _seed_series(reader_db_path, 1200, hr, speed)

    report = _report(reader_db_path)

    assert report is not None
    kinds = [moment["kind"] for moment in report["moments"]]
    assert "ceiling_touch" not in kinds
    # The stride and its 60 s recovery are what the ceiling does not judge.
    assert report["judged_share"]["hr"] == pytest.approx(1120 / 1200, abs=1e-3)


@pytest.mark.integration
def test_plan_block_hr_ceiling_off_by_time_over(reader_db_path: Path) -> None:
    """Six minutes and more above the ceiling is off plan under a low average.

    400 s at 155 in a 20-minute easy run averages 148 -- under the 150
    ceiling, and on plan by the old average rule. The ceiling is a guard, so
    the time above it decides (#1357).
    """
    _seed_easy_day(reader_db_path)
    _seed_series(
        reader_db_path,
        1200,
        lambda t: 155.0 if 300 <= t < 700 else 145.0,
        lambda t: _EASY_SPEED,
    )

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["seconds_over"] >= 360
    assert ceiling["pct_over"] > 6.0
    row = _ceiling_row(report)
    assert row["on_plan"] is False
    assert row["status"] == "off_plan"
    assert report["plan"]["verdict"] == "🟡"
