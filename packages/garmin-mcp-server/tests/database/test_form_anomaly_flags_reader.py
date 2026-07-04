"""Reader tests for the consolidated form-anomaly flags + signal (#809).

The material-event aggregation (deduped events, high-severity count, personal
baseline flag rule) now lives in ``GarminDBReader`` so both the injury-risk
signal and the web caution card share one scan. These tests drive the reader
against a minimal DuckDB and stub the detector at the ``db_reader`` import site
(the shared scan's single class binding), so no raw activity files are needed.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        total_distance_km DOUBLE,
        total_time_seconds INTEGER
    )
"""


def _build_db(tmp_path: Path, activities: list[tuple[int, str, int]]) -> Path:
    """Create a minimal DuckDB at <tmp>/database/garmin.duckdb with given runs.

    ``activities`` are ``(activity_id, activity_date, total_time_seconds)``.
    """
    db_dir = tmp_path / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "garmin.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.executemany(
            "INSERT INTO activities (activity_id, activity_date, "
            "total_distance_km, total_time_seconds) VALUES (?, ?, ?, ?)",
            [(aid, adate, 8.0, secs) for aid, adate, secs in activities],
        )
    finally:
        conn.close()
    return db_path


def _recent(days_ago: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()


def _anomaly(timestamp: int, z: float, cause: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "metric": "directGroundContactTime",
        "z_score": z,
        "probable_cause": cause,
    }


class _StubDetector:
    """Stub returning pre-built ``get_form_anomaly_details`` payloads by id."""

    def __init__(self, by_id: dict[int, list[dict[str, Any]]]) -> None:
        self._by_id = by_id

    def get_form_anomaly_details(
        self, activity_id: int, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"anomalies": self._by_id.get(int(activity_id), [])}


def _patch_detector(
    monkeypatch: pytest.MonkeyPatch, by_id: dict[int, list[dict[str, Any]]]
) -> None:
    """Replace the detector at the db_reader import site with a stub."""
    monkeypatch.setattr(
        "garmin_mcp.database.db_reader.FormAnomalyDetector",
        lambda base_path=None: _StubDetector(by_id),
    )


@pytest.mark.integration
def test_get_recent_form_anomaly_flags_no_raw_data(tmp_path: Path) -> None:
    """Recent runs without loadable raw data -> empty flags, no exception."""
    from tests.generate_verification_db import generate_verification_db

    db_path = tmp_path / "no_raw.duckdb"
    generate_verification_db(output_path=db_path)

    # Two recent runs whose raw details are absent under the derived base path.
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, "
            "total_time_seconds) VALUES (?, ?, ?)",
            (9300000001, _recent(1), 2400),
        )
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, "
            "total_time_seconds) VALUES (?, ?, ?)",
            (9300000002, _recent(3), 2400),
        )

    reader = GarminDBReader(db_path=str(db_path))
    result = reader.get_recent_form_anomaly_flags(weeks=2)

    assert result["weeks"] == 2
    assert result["limited"] is False
    assert result["flags"] == []
    assert isinstance(result["scanned"], int)
    assert result["scanned"] >= 2


@pytest.mark.integration
def test_get_recent_form_anomaly_flags_flags_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recent run with 3 material events over a low baseline -> 1 flag."""
    recent_id = 9310000001
    base1, base2 = 9310000002, 9310000003
    db_path = _build_db(
        tmp_path,
        [
            (recent_id, _recent(3), 1800),  # 0.5h, 3 events
            (base1, _recent(30), 3600),  # 1h, 1 event
            (base2, _recent(40), 3600),  # 1h, 1 event
        ],
    )
    _patch_detector(
        monkeypatch,
        {
            recent_id: [
                _anomaly(100, 5.0, "pace_change"),
                _anomaly(200, 4.0, "pace_change"),
                _anomaly(300, 4.0, "pace_change"),
            ],
            base1: [_anomaly(100, 4.0, "pace_change")],
            base2: [_anomaly(100, 4.0, "pace_change")],
        },
    )

    reader = GarminDBReader(db_path=str(db_path))
    result = reader.get_recent_form_anomaly_flags(weeks=2)

    assert result["scanned"] == 1
    assert result["limited"] is False
    assert len(result["flags"]) == 1

    flag = result["flags"][0]
    assert flag["activity_id"] == recent_id
    assert flag["anomalies_detected"] == 3
    assert flag["severity_high"] == 1
    assert flag["top_recommendation"]


@pytest.mark.integration
def test_form_anomaly_signal_unchanged_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refactored signal keeps its 6-key events/hour contract (#809)."""
    recent_id = 9320000001
    base_id = 9320000002
    db_path = _build_db(
        tmp_path,
        [
            (recent_id, _recent(3), 1800),  # 0.5h, 3 events
            (base_id, _recent(35), 3600),  # 1h, 1 event
        ],
    )
    _patch_detector(
        monkeypatch,
        {
            recent_id: [
                _anomaly(100, 5.0, "pace_change"),
                _anomaly(200, 4.0, "pace_change"),
                _anomaly(300, 4.0, "pace_change"),
            ],
            base_id: [_anomaly(100, 4.0, "pace_change")],
        },
    )

    reader = GarminDBReader(db_path=str(db_path))
    signal = reader._form_anomaly_signal(
        recent_start=_recent(13),
        end_date=dt.date.today().isoformat(),
        baseline_start=_recent(90),
    )

    assert signal is not None
    assert set(signal) == {
        "recent_rate",
        "baseline_rate",
        "recent_events",
        "baseline_events",
        "recent_hours",
        "baseline_hours",
    }
    assert signal["recent_events"] == 3
    assert signal["baseline_events"] == 1
    assert signal["recent_rate"] == pytest.approx(6.0)
    assert signal["baseline_rate"] == pytest.approx(1.0)
