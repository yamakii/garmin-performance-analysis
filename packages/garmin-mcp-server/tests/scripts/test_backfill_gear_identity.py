"""Tests for the gear identity backfill (Issue #1207)."""

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.backfill_gear_identity import backfill_gear_identity


def _write_gear(raw_dir: Path, activity_id: int, payload) -> None:
    activity_dir = raw_dir / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)
    (activity_dir / "gear.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def seeded(initialized_db_path: Path, tmp_path: Path, monkeypatch) -> Path:
    """Four activities: new-style gear, old-style gear, empty gear, no file."""
    raw_dir = tmp_path / "data" / "raw"
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path / "data"))

    conn = duckdb.connect(str(initialized_db_path))
    for activity_id, date in (
        (1, "2026-09-15"),
        (2, "2026-09-06"),
        (3, "2020-06-01"),
        (4, "2026-09-16"),
    ):
        conn.execute(
            """
            INSERT INTO activities (activity_id, activity_date, gear_model)
            VALUES (?, ?, ?)
            """,
            [activity_id, date, "Existing Model"],
        )
    conn.close()

    _write_gear(
        raw_dir,
        1,
        [
            {
                "uuid": "uuid-v15",
                "gearTypeName": "Shoes",
                "customMakeModel": "New Balance Fresh Foam X 1080",
                "displayName": "v15",
            }
        ],
    )
    _write_gear(
        raw_dir,
        2,
        [
            {
                "uuid": "uuid-v14",
                "gearTypeName": "Shoes",
                "customMakeModel": "nb 1080 v14",
                "displayName": None,
            }
        ],
    )
    _write_gear(raw_dir, 3, [])
    # Activity 4 deliberately has no raw directory at all.
    return initialized_db_path


@pytest.mark.integration
def test_backfill_populates_nickname_and_uuid(seeded: Path) -> None:
    result = backfill_gear_identity(db_path=str(seeded))

    assert result["activities_scanned"] == 4
    assert result["activities_updated"] == 2
    assert result["no_gear_registered"] == 1
    assert result["no_raw_file"] == 1

    conn = duckdb.connect(str(seeded), read_only=True)
    rows = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            "SELECT activity_id, gear_nickname, gear_uuid FROM activities"
        ).fetchall()
    }
    conn.close()

    assert rows[1] == ("v15", "uuid-v15")
    assert rows[2] == (None, "uuid-v14")
    assert rows[3] == (None, None)
    assert rows[4] == (None, None)


@pytest.mark.integration
def test_backfill_never_drops_existing_gear(seeded: Path) -> None:
    """The activity with no raw file keeps the gear_model it already had."""
    backfill_gear_identity(db_path=str(seeded))

    conn = duckdb.connect(str(seeded), read_only=True)
    models = [
        row[0]
        for row in conn.execute(
            "SELECT gear_model FROM activities ORDER BY activity_id"
        ).fetchall()
    ]
    conn.close()

    assert models == ["Existing Model"] * 4


@pytest.mark.integration
def test_backfill_dry_run_writes_nothing(seeded: Path) -> None:
    result = backfill_gear_identity(db_path=str(seeded), dry_run=True)

    assert result["dry_run"] is True
    assert result["activities_updated"] == 2

    conn = duckdb.connect(str(seeded), read_only=True)
    populated = conn.execute(
        "SELECT COUNT(*) FROM activities WHERE gear_uuid IS NOT NULL"
    ).fetchone()
    conn.close()

    assert populated is not None
    assert populated[0] == 0


@pytest.mark.integration
def test_backfill_is_idempotent(seeded: Path) -> None:
    first = backfill_gear_identity(db_path=str(seeded))
    second = backfill_gear_identity(db_path=str(seeded))

    assert first["activities_updated"] == second["activities_updated"] == 2

    conn = duckdb.connect(str(seeded), read_only=True)
    row = conn.execute(
        "SELECT gear_nickname, gear_uuid FROM activities WHERE activity_id = 1"
    ).fetchone()
    conn.close()

    assert row == ("v15", "uuid-v15")
