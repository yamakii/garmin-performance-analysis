"""Form metrics judged far outside the model's trained speed range (#1273).

The guard is graded, not binary: an easy run just past the edge stays judged,
a tempo run far beyond it is not judged at all -- and is kept out of the band
every other run is judged against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    _INSIDE_RANGE_PACE,
    _TEMPO_PACE,
    _VR_SPREAD,
    ACTIVITY_ID,
    TODAY,
    _day,
    _report,
    _seed_baseline,
    _seed_history,
    _seed_run,
    _signal,
)


@pytest.mark.integration
def test_tempo_run_form_signals_are_not_judged(reader_db_path: Path) -> None:
    """A tempo run judged by an easy-run model is a reference value, not a flag.

    2026-09-09 ran at 2.70 m/s against a baseline trained on 1.97-2.38 m/s and
    was told its vertical ratio was high -- an expectation the curve had never
    been asked for (#1273).
    """
    _seed_history(reader_db_path, pace_base=_INSIDE_RANGE_PACE)
    _seed_baseline(reader_db_path, speed_min=1.97, speed_max=2.38)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        pace=_TEMPO_PACE,
        training_type="tempo_run",
        vr_delta_pct=5 * _VR_SPREAD,
    )

    report = _report(reader_db_path)

    assert report is not None
    vr = _signal(report, "vr")
    assert vr["status"] == "insufficient"
    assert vr["z"] is None
    assert "速度の範囲" in vr["reason"]
    assert report["headline"]["flag_count"] == 0


@pytest.mark.integration
def test_slightly_outside_range_is_still_judged(reader_db_path: Path) -> None:
    """0.02 m/s past the edge is the everyday easy run, and it stays judged.

    A strict in/out test would silence it; the factor grades the distance
    (1.09 here against 2.33 for the tempo run above).
    """
    _seed_history(reader_db_path, pace_base=_INSIDE_RANGE_PACE)
    _seed_baseline(reader_db_path, speed_min=1.97, speed_max=2.38)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        pace=1000.0 / 2.40,
    )

    report = _report(reader_db_path)

    assert report is not None
    for metric in ("gct", "vo", "vr", "cadence"):
        assert "速度の範囲" not in (_signal(report, metric)["reason"] or "")
    # gct and vr are the two form series the fixture gives a spread to.
    assert _signal(report, "gct")["status"] == "within"
    assert _signal(report, "vr")["status"] == "within"


@pytest.mark.integration
def test_extrapolated_history_rows_do_not_shape_the_band(
    reader_db_path: Path,
) -> None:
    """A tempo run must not widen the band an easy run is judged against.

    Twelve easy runs at -0.5/+0.5 % give a centre of 0 and a spread of
    ``1.4826 * 0.5``: today's +1.6 % is 2.16 spreads out. Let the three tempo
    rows at +3.0 % in and the centre moves to +0.5 with a spread of 1.4826 --
    the same run then reads as 0.74, comfortably normal.
    """
    _seed_history(reader_db_path, pace_base=_INSIDE_RANGE_PACE)
    _seed_baseline(reader_db_path, speed_min=1.97, speed_max=2.38)
    for index, days_ago in enumerate((-1, -2, -4)):
        _seed_run(
            reader_db_path,
            activity_id=ACTIVITY_ID + 200 + index,
            activity_date=_day(days_ago),
            pace=_TEMPO_PACE,
            training_type="tempo_run",
            vr_delta_pct=3.0,
        )
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        pace=_INSIDE_RANGE_PACE + 10,
        vr_delta_pct=1.6,
    )

    report = _report(reader_db_path)

    assert report is not None
    vr = _signal(report, "vr")
    assert vr["status"] == "outside"
    assert vr["z"] == pytest.approx(2.16, abs=0.05)


@pytest.mark.integration
def test_power_signal_ignores_extrapolation(reader_db_path: Path) -> None:
    """The power model has no speed range, so no speed can extrapolate it."""
    _seed_history(reader_db_path, pace_base=_INSIDE_RANGE_PACE)
    _seed_baseline(reader_db_path, speed_min=1.97, speed_max=2.38)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        pace=_TEMPO_PACE,
        training_type="tempo_run",
    )

    report = _report(reader_db_path)

    assert report is not None
    power = _signal(report, "power")
    assert power["status"] == "within"
    assert power["reason"] is None
