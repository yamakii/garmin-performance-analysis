"""Tests for the sensor source backfill (Issue #1459)."""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.backfill_sensor_source import backfill_sensor_source


def _write_activity(raw_dir: Path, activity_id: int, sensors) -> None:
    activity_dir = raw_dir / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)
    (activity_dir / "activity.json").write_text(
        json.dumps({"metadataDTO": {"sensors": sensors}}), encoding="utf-8"
    )


def _sources(db_path: Path) -> dict[int, tuple]:
    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(
        "SELECT activity_id, dynamics_source, hr_source FROM activities"
    ).fetchall()
    conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


@pytest.fixture
def seeded(initialized_db_path: Path, tmp_path: Path, monkeypatch) -> Path:
    """Three activities: pod run, optical run (sensors null), no raw file."""
    raw_dir = tmp_path / "data" / "raw"
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path / "data"))

    conn = duckdb.connect(str(initialized_db_path))
    for activity_id, date in ((1, "2021-05-01"), (2, "2026-10-01"), (3, "2026-10-02")):
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
            [activity_id, date],
        )
    conn.close()

    _write_activity(
        raw_dir,
        1,
        [
            {
                "sourceType": "ANTPLUS",
                "antplusDeviceType": "RUN",
                "fitProductNumber": 2593,
            }
        ],
    )
    _write_activity(raw_dir, 2, None)
    # Activity 3 deliberately has no raw directory at all.
    return initialized_db_path


@pytest.mark.integration
def test_backfill_sensor_source_updates_rows(seeded: Path) -> None:
    dry = backfill_sensor_source(db_path=str(seeded), dry_run=True)
    assert dry["activities_updated"] == 2
    assert _sources(seeded) == {1: (None, None), 2: (None, None), 3: (None, None)}

    result = backfill_sensor_source(db_path=str(seeded))

    assert result["activities_scanned"] == 3
    assert result["activities_updated"] == 2
    assert result["no_raw_file"] == 1
    assert result["pod_runs"] == 1
    assert _sources(seeded) == {
        1: ("pod", "wrist"),
        2: ("wrist", "wrist"),
        3: (None, None),
    }
