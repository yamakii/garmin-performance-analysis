"""Run-to-run comparisons in the run report honour comparability (#1523).

A pod run compared with a wrist run differs in ground contact because the
sensor differs, and a run with a backpack differs in heart rate because of the
load. ``vs_previous`` drops the deltas such a pair cannot be compared on, the
recurrence look-back leaves out the runs whose heart rate is not comparable,
and the report says which sensors measured the run and how each metric came
to be.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)


def _set_sources(db_path: Path, *, everyone: str, today: str) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("UPDATE activities SET dynamics_source = ?", [everyone])
        conn.execute(
            "UPDATE activities SET dynamics_source = ? WHERE activity_id = ?",
            [today, ACTIVITY_ID],
        )
    finally:
        conn.close()


def _seed_load(db_path: Path, activity_id: int, load_kg: float) -> None:
    from garmin_mcp.database.inserters.athlete import insert_activity_context

    insert_activity_context(
        row={
            "activity_id": activity_id,
            "kind": "load",
            "value": "backpack",
            "load_kg": load_kg,
            "source": "athlete_stated",
            "note": None,
            "user_id": "default",
        },
        db_path=str(db_path),
    )


@pytest.mark.integration
def test_vs_previous_drops_gct_when_previous_is_wrist(reader_db_path: Path) -> None:
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _set_sources(reader_db_path, everyone="wrist", today="pod")

    report = _report(reader_db_path)

    assert report is not None
    vs_previous = report["vs_previous"]
    assert vs_previous is not None
    assert "gct_ms" not in vs_previous
    # HR and pace were measured alike, so they are still compared.
    assert "avg_hr" in vs_previous
    assert "pace_s_per_km" in vs_previous
    assert vs_previous["comparability"]["reasons"] == ["dynamics_source_differs"]
    assert "gct_ms" in vs_previous["comparability"]["excluded_metrics"]


@pytest.mark.integration
def test_vs_previous_same_sensor_keeps_every_delta(reader_db_path: Path) -> None:
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _set_sources(reader_db_path, everyone="wrist", today="wrist")

    report = _report(reader_db_path)

    assert report is not None
    vs_previous = report["vs_previous"]
    assert "gct_ms" in vs_previous
    assert vs_previous["comparability"] == {"excluded_metrics": [], "reasons": []}


@pytest.mark.integration
def test_recurrence_skips_loaded_previous_runs_for_hr_scenes(
    reader_db_path: Path,
) -> None:
    """5 previous runs, the 2 newest loaded: only the 3 unloaded are counted."""
    _seed_history(reader_db_path, count=5)
    _seed_run(
        reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY, split_hr=140
    )
    # A 135 ceiling under laps at 140: every run touches it at km 1.
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        title="イージー",
        target_km=None,
        target_minutes=30,
        hr_low=None,
        hr_high=135,
    )
    for index in (3, 4):
        _seed_load(reader_db_path, ACTIVITY_ID + 100 + index, 3.0)

    report = _report(reader_db_path)

    assert report is not None
    ceiling = [row for row in report["recurrence"] if row["kind"] == "ceiling_touch"]
    assert ceiling, report["recurrence"]
    assert ceiling[0]["of"] == 4
    assert ceiling[0]["count"] == 4
    assert len(ceiling[0]["dates"]) == 3


@pytest.mark.integration
def test_report_exposes_sensors_and_provenance(reader_db_path: Path) -> None:
    _seed_history(reader_db_path, count=3)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _set_sources(reader_db_path, everyone="wrist", today="pod")

    report = _report(reader_db_path)

    assert report is not None
    assert report["sensors"] == {"dynamics_source": "pod", "hr_source": None}
    assert report["provenance"]["stride_length_cm"] == "device_derived"
    assert report["provenance"]["gct_ms"] == "measured"
    assert report["provenance"]["avg_hr"] == "measured"
