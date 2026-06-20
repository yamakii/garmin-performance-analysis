"""Integration tests for weight range ingest (issue #461).

The weight raw directory is redirected to a per-test ``tmp_path`` and the
Garmin client is mocked (no network). Cached ``{date}.json`` files exercise the
cache-first path (no API call); their absence forces a mocked
``get_daily_weigh_ins`` call. Tests assert the day loop count, that cache hits
avoid both the API and the throttle sleep, and the ``with_data`` tally.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.ingest.weight_ingest import ingest_weight_range


def _weigh_in(date_str: str, weight_grams: float = 76000.0) -> dict[str, Any]:
    """A non-empty Garmin daily weigh-in payload (weight in grams)."""
    return {
        "dateWeightList": [
            {
                "date": date_str,
                "weight": weight_grams,
                "bmi": 24.5,
                "bodyFat": 18.0,
            }
        ]
    }


def _write_cache(weight_dir: Path, date_str: str, payload: dict[str, Any]) -> None:
    """Write a cached weight file (``{}`` is the empty/no-data marker)."""
    weight_dir.mkdir(parents=True, exist_ok=True)
    with open(weight_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


@pytest.mark.integration
def test_ingest_weight_range_loops_days(tmp_path: Path) -> None:
    """start=end-2 → collect_body_composition_data called 3x, ingested_days==3."""
    weight_dir = tmp_path / "weight"
    weight_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "test.duckdb"

    collect_mock = MagicMock(return_value=None)
    with (
        patch(
            "garmin_mcp.ingest.weight_ingest.get_weight_raw_dir",
            return_value=weight_dir,
        ),
        patch(
            "garmin_mcp.ingest.weight_ingest.collect_body_composition_data",
            collect_mock,
        ),
    ):
        result = ingest_weight_range(
            "2026-06-01", "2026-06-03", db_path=str(db_path), throttle_seconds=0.0
        )

    assert collect_mock.call_count == 3
    assert result["ingested_days"] == 3
    assert result["dates"] == ["2026-06-01", "2026-06-02", "2026-06-03"]


@pytest.mark.integration
def test_ingest_weight_range_cache_first_no_api(tmp_path: Path) -> None:
    """All days cached → API (get_daily_weigh_ins) and throttle sleep not used."""
    weight_dir = tmp_path / "weight"
    db_path = tmp_path / "test.duckdb"
    for date_str in ("2026-06-01", "2026-06-02", "2026-06-03"):
        _write_cache(weight_dir, date_str, _weigh_in(date_str))

    client = MagicMock()
    with (
        patch(
            "garmin_mcp.ingest.weight_ingest.get_weight_raw_dir",
            return_value=weight_dir,
        ),
        patch(
            "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
            return_value=client,
        ),
        patch("garmin_mcp.ingest.weight_ingest.time.sleep") as sleep_mock,
    ):
        result = ingest_weight_range(
            "2026-06-01", "2026-06-03", db_path=str(db_path), throttle_seconds=1.0
        )

    client.get_daily_weigh_ins.assert_not_called()
    sleep_mock.assert_not_called()
    assert result["ingested_days"] == 3
    assert result["with_data"] == 3


@pytest.mark.integration
def test_ingest_weight_range_counts_with_data(tmp_path: Path) -> None:
    """Two days with data, one empty marker → with_data==2, ingested_days==3."""
    weight_dir = tmp_path / "weight"
    db_path = tmp_path / "test.duckdb"
    _write_cache(weight_dir, "2026-06-01", _weigh_in("2026-06-01"))
    _write_cache(weight_dir, "2026-06-02", {})  # empty marker (no data)
    _write_cache(weight_dir, "2026-06-03", _weigh_in("2026-06-03"))

    with patch(
        "garmin_mcp.ingest.weight_ingest.get_weight_raw_dir",
        return_value=weight_dir,
    ):
        result = ingest_weight_range(
            "2026-06-01", "2026-06-03", db_path=str(db_path), throttle_seconds=0.0
        )

    assert result["ingested_days"] == 3
    assert result["with_data"] == 2
