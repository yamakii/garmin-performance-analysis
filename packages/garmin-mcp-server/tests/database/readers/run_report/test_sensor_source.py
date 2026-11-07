"""Form signals are judged only against runs from today's dynamics sensor (#1470).

2026-10-17 was the athlete's fourth run with the RD Pod back on, judged against
a window of wrist runs: vertical ratio 11.2 % against a 9.1-9.4 % "normal"
(z 26), every form metric outside -- a sensor offset, not a form change, and
the run note was rejected for not explaining it.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import (
    _VR_SPREAD,
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_run,
    _signal,
)


def _set_source(db_path: Path, source: str, *, today: str | None = None) -> None:
    """Stamp every run (or only today's when ``today`` is given) with a sensor."""
    conn = duckdb.connect(str(db_path))
    try:
        if today is None:
            conn.execute("UPDATE activities SET dynamics_source = ?", [source])
        else:
            conn.execute(
                "UPDATE activities SET dynamics_source = ? WHERE activity_id = ?",
                [source, ACTIVITY_ID],
            )
    finally:
        conn.close()


@pytest.mark.integration
def test_fetch_window_carries_dynamics_source(reader_db_path: Path) -> None:
    """A pod run over a wrist-only window is not judged, and says why."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        vr_delta_pct=5 * _VR_SPREAD,
    )
    _set_source(reader_db_path, "wrist")
    _set_source(reader_db_path, "pod", today=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    vr = _signal(report, "vr")
    assert vr["status"] == "insufficient"
    assert vr["adverse"] is False
    assert vr["reason_code"] == "sensor_thin_baseline"
    assert vr["reason"].startswith("ランニングポッドで測った直近のランが 0 本")
    assert report["headline"]["flag_count"] == 0


@pytest.mark.integration
def test_same_sensor_window_is_judged_as_before(reader_db_path: Path) -> None:
    """A wrist run over a wrist window keeps its verdict."""
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        vr_delta_pct=5 * _VR_SPREAD,
    )
    _set_source(reader_db_path, "wrist")

    report = _report(reader_db_path)

    assert report is not None
    vr = _signal(report, "vr")
    assert vr["status"] == "outside"
    assert vr["adverse"] is True
