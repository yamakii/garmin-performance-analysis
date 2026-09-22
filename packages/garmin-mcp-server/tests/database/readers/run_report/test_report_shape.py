"""The run report's payload: its key set, the headline and the degraded cases.

One activity in, one JSON-serialisable dict out -- including when the day had no
prescription, when the history is too thin to judge anything and when the
activity does not exist at all (#1250).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    _BASELINE_CENTRE,
    _BASELINE_SPREAD,
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
    _seed_zones,
    _signal,
)


@pytest.mark.integration
def test_run_report_shape_and_json(reader_db_path: Path) -> None:
    """Every top-level key is present and the payload survives json.dumps."""
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 129, 400.0), (2, 130, 149, 1386.0), (3, 150, 159, 321.0)],
    )

    report = _report(reader_db_path)

    assert report is not None
    assert set(report) == {
        "activity_id",
        "activity_date",
        "intensity_category",
        "headline",
        "plan",
        "judged_share",
        "signals",
        "zones",
        "moments",
        "flow",
        "recurrence",
        "phases",
        "conditions",
        "vs_previous",
        "next_run_target",
        "next_session",
    }
    assert report["activity_id"] == ACTIVITY_ID
    assert report["activity_date"] == TODAY
    assert report["intensity_category"] == "easy"
    assert len(report["signals"]) == 7
    assert [zone["zone"] for zone in report["zones"]] == [1, 2, 3]
    assert report["moments"], "an uneventful run still reports its steady scene"
    assert {phase["phase"] for phase in report["phases"]} == {
        "warmup",
        "run",
        "cooldown",
    }
    assert report["conditions"]["temp_c"] == 15.0
    assert report["vs_previous"] is not None

    # No custom encoder: dates are str and every number is a built-in.
    assert json.loads(json.dumps(report))["activity_id"] == ACTIVITY_ID


@pytest.mark.integration
def test_run_report_headline_no_flags(reader_db_path: Path) -> None:
    """A run that answers its prescription with no adverse signal is clean."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,  # 101 % of the 8.0 km target
        gct_delta_pct=_BASELINE_CENTRE,
    )
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [(1, 100, 129, 400.0), (2, 130, 149, 1386.0), (3, 150, 159, 321.0)],
    )
    _seed_prescription(reader_db_path, on_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["headline"] == {
        "plan_label": "処方どおり",
        "flag_count": 0,
        "flag_labels": [],
    }
    assert report["plan"]["verdict"] == "✅"
    assert report["plan"]["title"] == "イージー 8km"
    volume = next(c for c in report["plan"]["checks"] if c["axis"] == "volume")
    assert volume == {
        "axis": "volume",
        "target": "8.0km",
        "actual": "8.1km（101%）",
        "status": "on_plan",
        "on_plan": True,
    }


@pytest.mark.integration
def test_run_report_flags_adverse_signal_only(reader_db_path: Path) -> None:
    """Only the unfavourable outlier becomes a flag; a favourable one does not."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        # +2.4 spreads on the unfavourable side of the seeded gct baseline.
        gct_delta_pct=_BASELINE_CENTRE + 2.4 * _BASELINE_SPREAD,
        # Far below what pace / temperature / date predict: an outlier the
        # athlete benefits from, so it must not be reported as a flag.
        avg_hr=110,
    )

    report = _report(reader_db_path)

    assert report is not None
    gct = _signal(report, "gct")
    assert gct["z"] == pytest.approx(2.4, abs=0.05)
    assert gct["status"] == "outside"
    assert gct["adverse"] is True

    hr = _signal(report, "hr_vs_expected")
    assert hr["status"] == "outside"
    assert hr["z"] < 0
    assert hr["adverse"] is False

    assert report["headline"]["flag_count"] == 1
    assert report["headline"]["flag_labels"] == ["接地時間が長め"]


@pytest.mark.integration
def test_run_report_without_prescription(reader_db_path: Path) -> None:
    """An unprescribed day has no plan card and says so in the headline."""
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["plan"] is None
    assert report["headline"]["plan_label"] == "処方なし"


@pytest.mark.integration
def test_run_report_hr_ceiling_from_prescription(reader_db_path: Path) -> None:
    """Time above the ceiling is read off the HR zones, not the time series."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=144,
        distance_km=8.08,
    )
    _seed_zones(
        reader_db_path,
        ACTIVITY_ID,
        [
            (1, 100, 129, 400.0),
            (2, 130, 149, 1386.0),
            (3, 150, 159, 321.0),  # 2107 s total, 321 s at or above 150 bpm
        ],
    )
    _seed_prescription(reader_db_path, on_date=TODAY, hr_high=150)

    report = _report(reader_db_path)

    assert report is not None
    ceiling = report["plan"]["hr_ceiling"]
    assert ceiling["bpm"] == 150
    assert ceiling["seconds_over"] == 321.0
    assert ceiling["pct_over"] == pytest.approx(15.2, abs=0.2)


@pytest.mark.integration
def test_run_report_thin_history_is_insufficient_not_error(
    reader_db_path: Path,
) -> None:
    """Three prior runs judge nothing -- and raise nothing either."""
    _seed_history(reader_db_path, count=3)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert [signal["status"] for signal in report["signals"]] == ["insufficient"] * 7
    assert all(signal["reason"] for signal in report["signals"])
    assert report["headline"]["flag_count"] == 0


@pytest.mark.integration
def test_no_heat_model_reason_is_japanese(reader_db_path: Path) -> None:
    """Three prior runs fit no heat model, and the page says so in Japanese."""
    _seed_history(reader_db_path, count=3)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    hr = _signal(report, "hr_vs_expected")
    assert hr["status"] == "insufficient"
    assert hr["reason"] == "同じ種類のランが少なく、想定心拍を計算できない"
    assert hr["reason_code"] == "no_hr_model"


@pytest.mark.integration
def test_no_signal_reason_is_ascii_only(reader_db_path: Path) -> None:
    """No unjudged row may leak an internal English phrase to the reader (#1278)."""
    _seed_history(reader_db_path, count=3)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    unjudged = [s for s in report["signals"] if s["status"] == "insufficient"]
    assert len(unjudged) == 7
    for signal in unjudged:
        reason = signal["reason"]
        assert reason, signal["metric"]
        assert not reason.isascii(), f"{signal['metric']}: {reason}"
        assert signal["reason_code"].isascii()


@pytest.mark.integration
def test_run_report_unknown_activity_returns_none(reader_db_path: Path) -> None:
    """An activity the database has never seen has no report."""
    assert _report(reader_db_path, activity_id=1) is None
