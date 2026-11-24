"""``vs_previous`` finds the previous delivered session of the same kind (#1615).

On 2026-11-24 a 20-minute threshold run got no comparison: Garmin had filed
10/27's prescribed cruise intervals (Z3 block between warmup and cooldown) as
``aerobic_base``, so no previous *threshold* run existed. A run that answers a
quality prescription and spent >= 25 % of its time in zone 3+ now counts as that
session; one prescribed as threshold but run easy (11/17: Z3+ 13 %) does not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.run_report import _delivered_family
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _day,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)

_CRUISE = ACTIVITY_ID + 801  # 10/27: prescribed threshold, Z3+ 67.5 %
_RUN_EASY = ACTIVITY_ID + 802  # 11/17: prescribed threshold, Z3+ 13 %

_TODAY_ZONES = (6.9, 37.1, 14.4, 41.5, 0.0)
_CRUISE_ZONES = (3.1, 29.4, 66.6, 0.9, 0.0)
_EASY_ZONES = (8.3, 78.7, 13.0, 0.0, 0.0)


def _seed_today(db_path: Path) -> None:
    _seed_history(db_path)
    _seed_run(
        db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        pace=364.0,
        avg_hr=151,
        temp_c=10.6,
        distance_km=6.75,
        training_type="lactate_threshold",
        zone_pcts=_TODAY_ZONES,
    )
    _seed_prescription(
        db_path,
        on_date=TODAY,
        session_type="threshold",
        title="20分持続（〜162）",
        target_km=None,
        target_minutes=20,
        hr_low=155,
        hr_high=162,
        prescription_id=1,
    )


def _seed_cruise(db_path: Path) -> None:
    _seed_run(
        db_path,
        activity_id=_CRUISE,
        activity_date=_day(-28),
        pace=388.5,
        avg_hr=152,
        temp_c=17.8,
        distance_km=6.65,
        training_type="aerobic_base",
        zone_pcts=_CRUISE_ZONES,
    )
    _seed_prescription(
        db_path,
        on_date=_day(-28),
        session_type="threshold",
        title="クルーズ 2×10分（148-158）",
        target_km=None,
        target_minutes=20,
        hr_low=148,
        hr_high=158,
        prescription_id=2,
    )


@pytest.mark.integration
def test_vs_previous_finds_prescribed_quality_session_filed_as_easy(
    reader_db_path: Path,
) -> None:
    _seed_today(reader_db_path)
    _seed_cruise(reader_db_path)

    report = _report(reader_db_path)

    assert report is not None
    vs_previous = report["vs_previous"]
    assert vs_previous is not None
    assert vs_previous["previous_activity_id"] == _CRUISE
    assert vs_previous["previous_session_title"] == "クルーズ 2×10分（148-158）"


@pytest.mark.integration
def test_vs_previous_skips_prescribed_session_not_run_at_intensity(
    reader_db_path: Path,
) -> None:
    _seed_today(reader_db_path)
    _seed_cruise(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=_RUN_EASY,
        activity_date=_day(-7),
        pace=404.0,
        avg_hr=143,
        training_type="aerobic_base",
        zone_pcts=_EASY_ZONES,
    )
    _seed_prescription(
        reader_db_path,
        on_date=_day(-7),
        session_type="threshold",
        title="10分×2 つなぎ90秒（〜158）",
        target_km=None,
        target_minutes=20,
        hr_low=None,
        hr_high=158,
        prescription_id=3,
    )

    report = _report(reader_db_path)

    assert report is not None
    assert report["vs_previous"]["previous_activity_id"] == _CRUISE


@pytest.mark.integration
def test_vs_previous_conditions_pair(reader_db_path: Path) -> None:
    _seed_today(reader_db_path)
    _seed_cruise(reader_db_path)

    report = _report(reader_db_path)

    assert report is not None
    conditions = report["vs_previous"]["conditions"]
    assert conditions["temp_c"]["current"] == pytest.approx(10.6)
    assert conditions["temp_c"]["previous"] == pytest.approx(17.8)
    assert conditions["temp_c"]["delta"] == pytest.approx(-7.2)
    assert conditions["z3_plus_pct"]["current"] == pytest.approx(55.9)
    assert conditions["z3_plus_pct"]["previous"] == pytest.approx(67.5)
    assert set(conditions["hr_source"]) == {"current", "previous"}


@pytest.mark.integration
def test_vs_previous_unprescribed_keeps_intensity_family(
    reader_db_path: Path,
) -> None:
    """No prescriptions: the previous same-family easy run, as before."""
    _seed_history(reader_db_path)
    previous = ACTIVITY_ID + 803
    _seed_run(reader_db_path, activity_id=previous, activity_date=_day(-1))
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["vs_previous"]["previous_activity_id"] == previous
    assert report["vs_previous"]["previous_session_title"] is None


@pytest.mark.unit
def test_session_family_threshold_constant() -> None:
    threshold = {"session_type": "threshold"}
    assert _delivered_family(threshold, {"z3_plus_pct": 24.9}) is None
    assert _delivered_family(threshold, {"z3_plus_pct": 25.0}) == "threshold"
    assert _delivered_family({"session_type": "easy"}, {"z3_plus_pct": 80.0}) is None
    assert _delivered_family(None, {"z3_plus_pct": 80.0}) is None
