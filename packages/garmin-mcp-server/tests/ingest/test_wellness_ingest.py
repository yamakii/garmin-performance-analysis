"""Integration tests for daily wellness range ingest (issue #498).

The wellness raw directory is redirected to a per-test ``tmp_path`` and the
Garmin client is mocked (no network). Cached ``{date}.json`` files exercise the
cache-first path (no API call, no throttle sleep). Verifies the day-window
fill, the ``with_data`` tally, and that the rows land in ``daily_wellness``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.ingest.wellness_ingest import ingest_wellness_range


def _wellness_payload(rhr: int = 48) -> dict[str, Any]:
    """A non-empty merged wellness payload."""
    return {
        "stats": {"restingHeartRate": rhr, "averageStressLevel": 30},
        "hrv": {
            "hrvSummary": {
                "lastNightAvg": 60,
                "status": "BALANCED",
                "baseline": {"lowUpper": 55, "balancedUpper": 75},
            }
        },
        "sleep": {
            "dailySleepDTO": {
                "sleepTimeSeconds": 26000,
                "sleepScores": {"overall": {"value": 80}},
            }
        },
        "training_readiness": [{"score": 70}],
    }


def _write_cache(wellness_dir: Path, date_str: str, payload: dict[str, Any]) -> None:
    wellness_dir.mkdir(parents=True, exist_ok=True)
    with open(wellness_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


@pytest.mark.integration
def test_ingest_wellness_range_fills_window(tmp_path: Path) -> None:
    """3 cached days → with_data==3, 3 rows in daily_wellness, no throttle."""
    wellness_dir = tmp_path / "wellness"
    db_path = tmp_path / "test.duckdb"
    dates = ["2026-06-20", "2026-06-21", "2026-06-22"]
    for i, date_str in enumerate(dates):
        _write_cache(wellness_dir, date_str, _wellness_payload(rhr=48 + i))

    with (
        patch(
            "garmin_mcp.ingest.wellness_ingest.get_wellness_raw_dir",
            return_value=wellness_dir,
        ),
        patch("garmin_mcp.ingest.wellness_ingest.time.sleep") as sleep_mock,
    ):
        result = ingest_wellness_range(
            "2026-06-20", "2026-06-22", db_path=str(db_path), throttle_seconds=1.0
        )

    # Cache hits → no throttle sleep between days.
    sleep_mock.assert_not_called()
    assert result["ingested_days"] == 3
    assert result["with_data"] == 3
    assert result["dates"] == dates

    with get_connection(str(db_path)) as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM daily_wellness").fetchone()
    assert count_row is not None and count_row[0] == 3
