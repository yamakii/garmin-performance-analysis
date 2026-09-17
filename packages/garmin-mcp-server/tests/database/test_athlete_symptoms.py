"""Integration tests for the symptom log inserter + reader (Issue #1220)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.inserters.athlete import insert_symptom
from garmin_mcp.database.readers.athlete import AthleteReader


def _calf_row() -> dict:
    return {
        "date": "2026-09-18",
        "body_region": "calf",
        "side": "right",
        "severity": 3,
        "phase": "morning",
        "note": "ロング翌朝の張り",
    }


@pytest.mark.integration
def test_insert_and_read_back(initialized_db_path) -> None:
    """One saved report comes back with its id and a string date."""
    db_path = str(initialized_db_path)

    symptom_id = insert_symptom(_calf_row(), db_path=db_path)

    rows = AthleteReader(db_path=db_path).get_symptoms("2026-09-01", "2026-09-30")
    assert len(rows) == 1
    row = rows[0]
    assert row["symptom_id"] == symptom_id
    assert row["date"] == "2026-09-18"
    assert row["user_id"] == "default"
    assert row["body_region"] == "calf"
    assert row["side"] == "right"
    assert row["severity"] == 3
    assert row["phase"] == "morning"
    assert row["activity_id"] is None
    assert row["note"] == "ロング翌朝の張り"


@pytest.mark.integration
def test_severity_zero_row_is_kept(initialized_db_path) -> None:
    """An explicit all-clear is stored, not filtered: asked-and-clear != unasked."""
    db_path = str(initialized_db_path)
    insert_symptom(
        {
            "date": "2026-09-18",
            "body_region": "achilles",
            "severity": 0,
            "phase": "after_run",
            "activity_id": 20636804823,
        },
        db_path=db_path,
    )

    rows = AthleteReader(db_path=db_path).get_symptoms("2026-09-18", "2026-09-18")

    assert [(r["body_region"], r["severity"]) for r in rows] == [("achilles", 0)]
    assert rows[0]["activity_id"] == 20636804823


@pytest.mark.integration
def test_filter_by_region_and_range(initialized_db_path) -> None:
    """Region filter and date range both narrow; rows come back oldest first."""
    db_path = str(initialized_db_path)
    for row in (
        {
            "date": "2026-09-16",
            "body_region": "calf",
            "severity": 2,
            "phase": "after_run",
        },
        {
            "date": "2026-09-17",
            "body_region": "knee",
            "severity": 5,
            "phase": "morning",
        },
        {
            "date": "2026-09-18",
            "body_region": "calf",
            "severity": 4,
            "phase": "during_run",
        },
    ):
        insert_symptom(row, db_path=db_path)

    reader = AthleteReader(db_path=db_path)

    all_rows = reader.get_symptoms("2026-09-16", "2026-09-18")
    assert [r["date"] for r in all_rows] == ["2026-09-16", "2026-09-17", "2026-09-18"]

    calf_rows = reader.get_symptoms("2026-09-16", "2026-09-18", body_region="calf")
    assert [(r["date"], r["severity"]) for r in calf_rows] == [
        ("2026-09-16", 2),
        ("2026-09-18", 4),
    ]

    # The range is inclusive on both ends and excludes everything outside it.
    narrowed = reader.get_symptoms("2026-09-17", "2026-09-18")
    assert [r["body_region"] for r in narrowed] == ["knee", "calf"]


@pytest.mark.integration
def test_reader_missing_table_returns_empty(tmp_path: Path) -> None:
    """A database older than the migration reads as 'nothing logged', not an error."""
    db_path = tmp_path / "legacy.duckdb"
    duckdb.connect(str(db_path)).close()

    rows = AthleteReader(db_path=str(db_path)).get_symptoms("2026-09-01", "2026-09-30")

    assert rows == []
