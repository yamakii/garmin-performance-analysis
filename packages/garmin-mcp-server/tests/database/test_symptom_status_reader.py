"""Integration tests for ``GarminDBReader.get_symptom_status`` (#1223).

Rows are written through the real inserter into a tmp DuckDB, then read back
through the reader so the window arithmetic and the rule are exercised
together. No production data, no Garmin access.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.database.inserters.athlete import insert_symptom

_REF = date(2026, 9, 18)


def _save(
    db_path: Path,
    days_ago: int,
    severity: int,
    body_region: str = "calf",
    side: str | None = "right",
) -> None:
    insert_symptom(
        {
            "date": str(_REF - timedelta(days=days_ago)),
            "body_region": body_region,
            "side": side,
            "severity": severity,
            "phase": "morning",
        },
        db_path=str(db_path),
    )


@pytest.mark.integration
def test_status_reader_window_is_14_days(initialized_db_path: Path) -> None:
    """A severity-5 report is acute at 6 days old but not at 8 (7-day window)."""
    _save(initialized_db_path, days_ago=8, severity=5)

    reader = GarminDBReader(db_path=str(initialized_db_path))
    status = reader.get_symptom_status(str(_REF))

    assert status["flag"] is False
    assert status["flagged_regions"] == []
    assert status["days_since_last_report"] == 8
    # The MCP boundary: the payload must survive json.dumps as-is.
    assert json.loads(json.dumps(status))["flag"] is False

    _save(initialized_db_path, days_ago=6, severity=5)
    status = reader.get_symptom_status(str(_REF))

    assert status["flag"] is True
    assert status["flagged_regions"][0]["rule"] == "acute"
    assert status["days_since_last_report"] == 6


@pytest.mark.integration
def test_status_reader_ignores_rows_older_than_the_window(
    initialized_db_path: Path,
) -> None:
    """Reports 15+ days old are outside the rule's window entirely."""
    _save(initialized_db_path, days_ago=20, severity=6)

    status = GarminDBReader(db_path=str(initialized_db_path)).get_symptom_status(
        str(_REF)
    )

    assert status["flag"] is False
    assert status["days_since_last_report"] is None
    assert status["asked_today"] is False


@pytest.mark.integration
def test_status_reader_reads_an_explicit_all_clear(initialized_db_path: Path) -> None:
    """A severity-0 row dated the reference day is the asked-and-clear record."""
    _save(initialized_db_path, days_ago=0, severity=0, body_region="other", side=None)

    status = GarminDBReader(db_path=str(initialized_db_path)).get_symptom_status(
        str(_REF)
    )

    assert status["asked_today"] is True
    assert status["clear_today"] is True
    assert status["flag"] is False


@pytest.mark.integration
def test_injury_risk_includes_the_symptom_factor(initialized_db_path: Path) -> None:
    """A flagged region reaches get_injury_risk as the ``symptom`` factor."""
    _save(initialized_db_path, days_ago=2, severity=4)
    _save(initialized_db_path, days_ago=0, severity=3)

    result = GarminDBReader(db_path=str(initialized_db_path)).get_injury_risk(
        date=str(_REF)
    )

    assert "symptom" in result["available_inputs"]
    symptom_factor = next(f for f in result["factors"] if f["name"] == "symptom")
    assert symptom_factor["contribution"] > 0
    assert "ふくらはぎ" in symptom_factor["detail_ja"]
