"""Tests for the daily_energy row mapping and writer upsert (issue #1433)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_writer import GarminDBWriter, _energy_row
from garmin_mcp.ingest.energy_ingest import ingest_energy_range


def _snapshot(consumed: int, fetched_at: str = "2026-09-23T09:00:00") -> dict[str, Any]:
    return {
        "fetched_at": fetched_at,
        "first_fetched_at": "2026-09-22T10:21:00",
        "summary": {
            "durationInMilliseconds": 37_260_000,
            "measurableAwakeDuration": 9_060,
            "measurableAsleepDuration": 22_020,
            "consumedKilocalories": consumed,
            "includesCalorieConsumedData": True,
            "totalKilocalories": 1_850,
            "activeKilocalories": 420,
            "bmrKilocalories": 1_430,
            "totalSteps": 8_123,
        },
        "revisions": [
            {
                "fetched_at": "2026-09-22T10:21:00",
                "coverage_seconds": 37_260,
                "consumed_kcal": consumed,
            }
        ],
    }


@pytest.mark.unit
def test_energy_row_maps_summary() -> None:
    """Summary fields map onto the daily_energy columns (ms -> s)."""
    row = _energy_row("2026-09-22", _snapshot(909))

    assert row is not None
    assert row["date"] == "2026-09-22"
    assert row["coverage_seconds"] == 37_260
    assert row["awake_seconds"] == 9_060
    assert row["asleep_seconds"] == 22_020
    assert row["consumed_kcal"] == 909
    assert row["includes_consumed"] is True
    assert row["total_kcal"] == 1_850
    assert row["active_kcal"] == 420
    assert row["bmr_kcal"] == 1_430
    assert row["total_steps"] == 8_123
    assert row["post_close_revisions"] == 0
    assert row["consumed_changed_at"] == "2026-09-22T10:21:00"


@pytest.mark.unit
def test_energy_row_without_summary_is_none() -> None:
    """A snapshot with no summary yields no row."""
    assert _energy_row("2026-09-22", {"fetched_at": "2026-09-23T09:00:00"}) is None


@pytest.mark.unit
def test_insert_daily_energy_replaces_row(initialized_db_path: Path) -> None:
    """Inserting the same date twice keeps one row holding the latest values."""
    writer = GarminDBWriter(db_path=str(initialized_db_path))

    assert writer.insert_daily_energy("2026-09-22", _snapshot(909)) is True
    assert (
        writer.insert_daily_energy(
            "2026-09-22", _snapshot(1_612, fetched_at="2026-09-24T09:00:00")
        )
        is True
    )

    with get_connection(str(initialized_db_path)) as conn:
        rows = conn.execute(
            "SELECT consumed_kcal, CAST(fetched_at AS VARCHAR) FROM daily_energy "
            "WHERE date = '2026-09-22'"
        ).fetchall()

    assert rows == [(1_612, "2026-09-24 09:00:00")]


@pytest.mark.integration
def test_ingest_energy_range_serves_settled_cache(
    initialized_db_path: Path, tmp_path: Path
) -> None:
    """Settled cached days are ingested without any Garmin call or throttle."""
    energy_dir = tmp_path / "energy"
    energy_dir.mkdir()
    for date_str, consumed in (("2026-09-01", 1_500), ("2026-09-02", 0)):
        with open(energy_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
            json.dump(_snapshot(consumed, fetched_at="2026-09-20T09:00:00"), f)

    client = MagicMock()
    with (
        patch(
            "garmin_mcp.ingest.energy_ingest.get_energy_raw_dir",
            return_value=energy_dir,
        ),
        patch(
            "garmin_mcp.ingest.energy_fetcher.get_garmin_client",
            return_value=client,
        ) as get_client,
        patch("garmin_mcp.ingest.energy_ingest.time.sleep") as sleep_mock,
    ):
        result = ingest_energy_range(
            "2026-09-01",
            "2026-09-02",
            db_path=str(initialized_db_path),
            now=datetime(2026, 9, 26, 9, 0),
        )

    get_client.assert_not_called()
    sleep_mock.assert_not_called()
    assert result == {
        "ingested_days": 2,
        "with_intake": 1,
        "dates": ["2026-09-01", "2026-09-02"],
    }
    with get_connection(str(initialized_db_path)) as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM daily_energy").fetchone()
    assert count_row is not None and count_row[0] == 2
