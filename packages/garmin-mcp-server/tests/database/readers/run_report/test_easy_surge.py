"""An easy run does not tell surge scenes (#1496).

The surge rule reads any kilometre 8 s/km faster than the run's median. On an
easy run that is the warm-up kilometre setting the median, not a finding, and
"km 2 again, 3 runs of 5" is the same artefact. A pickup that mattered crossed
the ceiling and is a ceiling_touch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.analysis.run_moments import without_kinds
from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
    _seed_splits,
)

# km 2 is 15 s/km faster than the 420 s/km median.
_LAPS: list[tuple[float, float, str | None]] = [
    (1.0, 420.0, None),
    (1.0, 405.0, None),
    (1.0, 425.0, None),
    (1.0, 420.0, None),
]


def _seed(db_path: Path, *, session_type: str, title: str) -> None:
    _seed_history(db_path)
    _seed_run(
        db_path,
        activity_id=ACTIVITY_ID,
        activity_date=TODAY,
        avg_hr=140,
        distance_km=4.0,
        duration_s=1670,
    )
    _seed_splits(db_path, ACTIVITY_ID, _LAPS)
    _seed_prescription(
        db_path,
        on_date=TODAY,
        session_type=session_type,
        title=title,
        target_km=4.0,
        hr_low=None,
        hr_high=150,
    )


@pytest.mark.integration
def test_easy_run_drops_surge_scene(reader_db_path: Path) -> None:
    _seed(reader_db_path, session_type="easy", title="イージー 4km")

    report = _report(reader_db_path)

    assert report is not None
    assert report["purpose"]["id"] == "easy"
    kinds = [m["kind"] for m in report["moments"]]
    assert "surge" not in kinds
    assert [m["id"] for m in report["moments"]] == [
        f"m{n}" for n in range(1, len(kinds) + 1)
    ]


@pytest.mark.integration
def test_easy_run_drops_surge_recurrence(reader_db_path: Path) -> None:
    _seed(reader_db_path, session_type="easy", title="イージー 4km")
    for index in range(7, 12):
        _seed_splits(reader_db_path, ACTIVITY_ID + 100 + index, _LAPS)

    report = _report(reader_db_path)

    assert report is not None
    assert not any(row["kind"] == "surge" for row in report["recurrence"])


@pytest.mark.integration
def test_unprescribed_or_tempo_run_keeps_surge(reader_db_path: Path) -> None:
    _seed(reader_db_path, session_type="tempo", title="テンポ 4km")

    report = _report(reader_db_path)

    assert report is not None
    assert report["purpose"]["id"] not in {"easy", "recovery", "long_easy"}
    assert "surge" in [m["kind"] for m in report["moments"]]


@pytest.mark.unit
def test_without_kinds_renumbers() -> None:
    moments = [
        {"id": "m1", "kind": "start"},
        {"id": "m2", "kind": "surge"},
        {"id": "m3", "kind": "steady"},
    ]

    out = without_kinds(moments, frozenset({"surge"}))

    assert out == [{"id": "m1", "kind": "start"}, {"id": "m2", "kind": "steady"}]
