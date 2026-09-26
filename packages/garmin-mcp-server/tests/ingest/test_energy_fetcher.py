"""Unit tests for the settle-aware daily energy fetcher (issue #1433).

The energy raw dir is a per-test ``tmp_path`` and the Garmin client is mocked,
so no network access occurs. ``now`` is injected so settle decisions are
deterministic.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.database.db_writer import _energy_row
from garmin_mcp.ingest.energy_fetcher import collect_energy_data

_DATE = "2026-09-22"


def _summary(coverage_seconds: int, consumed: int | None) -> dict[str, Any]:
    return {
        "durationInMilliseconds": coverage_seconds * 1000,
        "consumedKilocalories": consumed,
        "totalKilocalories": 2400,
    }


def _write_cache(energy_dir: Path, payload: dict[str, Any]) -> Path:
    energy_dir.mkdir(parents=True, exist_ok=True)
    path = energy_dir / f"{_DATE}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def _cached_snapshot(fetched_at: str) -> dict[str, Any]:
    return {
        "fetched_at": fetched_at,
        "first_fetched_at": "2026-09-22T20:00:00",
        "summary": _summary(86_400, 1_612),
        "revisions": [
            {
                "fetched_at": "2026-09-22T20:00:00",
                "coverage_seconds": 86_400,
                "consumed_kcal": 1_612,
            }
        ],
    }


def _client(*summaries: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    client.get_user_summary.side_effect = list(summaries)
    return client


@pytest.mark.unit
def test_collect_energy_refetches_until_settled(tmp_path: Path) -> None:
    """A snapshot fetched only 1 day after the date is re-fetched."""
    energy_dir = tmp_path / "energy"
    _write_cache(energy_dir, _cached_snapshot("2026-09-23T09:00:00"))
    client = _client(_summary(86_400, 1_612))

    with patch(
        "garmin_mcp.ingest.energy_fetcher.get_garmin_client", return_value=client
    ):
        result = collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 26, 9, 0))

    client.get_user_summary.assert_called_once_with(_DATE)
    assert result is not None
    assert result["fetched_at"] == "2026-09-26T09:00:00"
    assert result["first_fetched_at"] == "2026-09-22T20:00:00"
    on_disk = json.loads((energy_dir / f"{_DATE}.json").read_text(encoding="utf-8"))
    assert on_disk["fetched_at"] == "2026-09-26T09:00:00"
    # Intake unchanged -> no new revision.
    assert len(on_disk["revisions"]) == 1


@pytest.mark.unit
def test_collect_energy_uses_cache_once_settled(tmp_path: Path) -> None:
    """fetched_at >= date + 7 days -> the cache is final, no API call."""
    energy_dir = tmp_path / "energy"
    cached = _cached_snapshot("2026-09-29T09:00:00")
    _write_cache(energy_dir, cached)
    client = MagicMock()

    with patch(
        "garmin_mcp.ingest.energy_fetcher.get_garmin_client", return_value=client
    ) as get_client:
        result = collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 30, 9, 0))

    get_client.assert_not_called()
    client.get_user_summary.assert_not_called()
    assert result == cached


@pytest.mark.unit
def test_collect_energy_counts_only_post_close_revisions(tmp_path: Path) -> None:
    """Only the intake change between two full-day fetches is post-close."""
    energy_dir = tmp_path / "energy"
    client = _client(
        _summary(31_140, 0),
        _summary(86_400, 1_612),
        _summary(86_400, 1_505),
    )

    with patch(
        "garmin_mcp.ingest.energy_fetcher.get_garmin_client", return_value=client
    ):
        collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 22, 8, 39))
        collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 23, 9, 0))
        result = collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 24, 9, 0))

    assert result is not None
    assert [r["consumed_kcal"] for r in result["revisions"]] == [0, 1_612, 1_505]
    assert result["first_fetched_at"] == "2026-09-22T08:39:00"

    row = _energy_row(_DATE, result)
    assert row is not None
    assert row["post_close_revisions"] == 1
    assert row["consumed_changed_at"] == "2026-09-24T09:00:00"


@pytest.mark.unit
def test_collect_energy_keeps_cache_on_api_error(tmp_path: Path) -> None:
    """API error -> cached dict returned, file bytes untouched, no marker."""
    energy_dir = tmp_path / "energy"
    cached = _cached_snapshot("2026-09-23T09:00:00")
    path = _write_cache(energy_dir, cached)
    before = path.read_bytes()
    client = MagicMock()
    client.get_user_summary.side_effect = RuntimeError("garmin down")

    with patch(
        "garmin_mcp.ingest.energy_fetcher.get_garmin_client", return_value=client
    ):
        result = collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 26, 9, 0))

    assert result == cached
    assert path.read_bytes() == before
    assert sorted(p.name for p in energy_dir.iterdir()) == [f"{_DATE}.json"]


@pytest.mark.unit
def test_collect_energy_api_error_without_cache_writes_nothing(
    tmp_path: Path,
) -> None:
    """No cache + API error -> None and no file (no marker) is written."""
    energy_dir = tmp_path / "energy"
    client = MagicMock()
    client.get_user_summary.side_effect = RuntimeError("garmin down")

    with patch(
        "garmin_mcp.ingest.energy_fetcher.get_garmin_client", return_value=client
    ):
        result = collect_energy_data(energy_dir, _DATE, now=datetime(2026, 9, 26, 9, 0))

    assert result is None
    assert not energy_dir.exists()
