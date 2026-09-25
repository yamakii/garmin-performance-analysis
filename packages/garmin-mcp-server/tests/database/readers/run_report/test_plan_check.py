"""The plan card's per-axis rows (#1268, #1273).

Both sides of a row speak one language: the intensity row compares intensity
families (with the session word kept as a parenthesis on the target) and the
ceiling row is written the way a coach says it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)


@pytest.mark.integration
def test_plan_check_intensity_uses_one_vocabulary(reader_db_path: Path) -> None:
    """``easy`` vs ``aerobic_base`` is one intensity, so it reads as one.

    Two vocabularies made an on-plan row look like a mismatch.
    """
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,
        training_type="aerobic_base",
    )
    _seed_prescription(reader_db_path, on_date=TODAY, session_type="easy")

    report = _report(reader_db_path)

    assert report is not None
    intensity = next(c for c in report["plan"]["checks"] if c["axis"] == "intensity")
    assert intensity["target"] == "イージー"
    assert intensity["actual"] == "イージー"
    assert intensity["on_plan"] is True


@pytest.mark.integration
def test_plan_check_hr_ceiling_wording(reader_db_path: Path) -> None:
    """The ceiling is written the way a coach says it, not as a formula."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,
    )
    _seed_prescription(reader_db_path, on_date=TODAY, hr_high=150)

    report = _report(reader_db_path)

    assert report is not None
    ceiling = next(c for c in report["plan"]["checks"] if c["axis"] == "hr_ceiling")
    assert ceiling["target"] == "150 bpm 以下"
    assert ceiling["actual"] == "144 bpm"
    # A legacy easy row keeps its whole-run ceiling row, now in the AxisResult
    # shape (#1406).
    assert ceiling["label_ja"] == "心拍上限"
    assert ceiling["verdict"] == "✅"
    assert ceiling["segments"] == []


@pytest.mark.integration
def test_plan_check_long_run_shows_intensity_family_on_both_sides(
    reader_db_path: Path,
) -> None:
    """A long run answers an easy-intensity plan, and the row says so (#1273).

    The prescription's ``long`` names the session, the run's family names the
    intensity; printing one against the other made an on-plan long run read as
    a mismatch. The session word survives as a parenthesis on the target.
    """
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=16.0,
        training_type="aerobic_base",
    )
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="long",
        title="ロング 16km",
        target_km=16.0,
    )

    report = _report(reader_db_path)

    assert report is not None
    intensity = next(c for c in report["plan"]["checks"] if c["axis"] == "intensity")
    assert intensity["target"] == "イージー（ロング走）"
    assert intensity["actual"] == "イージー"
    assert intensity["on_plan"] is True


@pytest.mark.integration
def test_plan_check_easy_run_has_no_suffix(reader_db_path: Path) -> None:
    """A session type that says nothing beyond its family gets no parenthesis."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,
    )
    _seed_prescription(reader_db_path, on_date=TODAY, session_type="easy")

    report = _report(reader_db_path)

    assert report is not None
    intensity = next(c for c in report["plan"]["checks"] if c["axis"] == "intensity")
    assert intensity["target"] == "イージー"


@pytest.mark.integration
def test_plan_card_volume_pct_matches_verdict(reader_db_path: Path) -> None:
    """A 20-min threshold body plus its 15-min bookends is 100% of plan (#1399).

    The card used to divide the whole 35-min run by the body alone (175%)
    while reconciliation counted the bookends.
    """
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=160,
        distance_km=6.5,
        duration_s=35 * 60,
        training_type="lactate_threshold",
    )
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="threshold",
        title="閾値 20分",
        target_km=None,
        target_minutes=20,
        hr_low=None,
        hr_high=None,
    )

    report = _report(reader_db_path)

    assert report is not None
    volume = next(c for c in report["plan"]["checks"] if c["axis"] == "volume")
    assert volume["target"] == "35分"
    assert volume["actual"] == "35分（100%）"
    assert volume["on_plan"] is True
