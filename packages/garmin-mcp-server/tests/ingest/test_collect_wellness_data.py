"""Unit tests for collect_wellness_data cache-first behaviour (issue #498).

The wellness raw dir is a per-test ``tmp_path``; the Garmin client is mocked so
no network access occurs. A present ``{date}.json`` exercises the cache-first
path (no API call); an empty ``{}`` marker short-circuits to ``None``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.ingest.raw_data_fetcher import collect_wellness_data


def _write_cache(wellness_dir: Path, date_str: str, payload: dict[str, Any]) -> None:
    """Write a cached wellness file (``{}`` is the empty/no-data marker)."""
    wellness_dir.mkdir(parents=True, exist_ok=True)
    with open(wellness_dir / f"{date_str}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


@pytest.mark.unit
def test_collect_wellness_cache_hit_skips_api(tmp_path: Path) -> None:
    """Present non-empty cache → API client never constructed, cache returned."""
    wellness_dir = tmp_path / "wellness"
    cached = {"stats": {"restingHeartRate": 48}}
    _write_cache(wellness_dir, "2026-06-22", cached)

    client = MagicMock()
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ) as get_client:
        result = collect_wellness_data(wellness_dir, "2026-06-22")

    get_client.assert_not_called()
    client.get_stats.assert_not_called()
    assert result == cached


@pytest.mark.unit
def test_collect_wellness_empty_marker_returns_none(tmp_path: Path) -> None:
    """Empty ``{}`` marker → None and no API call."""
    wellness_dir = tmp_path / "wellness"
    _write_cache(wellness_dir, "2026-06-22", {})

    client = MagicMock()
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ) as get_client:
        result = collect_wellness_data(wellness_dir, "2026-06-22")

    get_client.assert_not_called()
    assert result is None


@pytest.mark.unit
def test_wellness_current_day_incomplete_not_saved(tmp_path: Path) -> None:
    """Current-day fetch with no sleep → None and no file written."""
    wellness_dir = tmp_path / "wellness"
    client = MagicMock()
    client.get_sleep_data.return_value = None
    client.get_hrv_data.return_value = None
    client.get_stats.return_value = None
    client.get_training_readiness.return_value = {"score": 46}

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_wellness_data(
            wellness_dir, "2026-06-25", today=date(2026, 6, 25)
        )

    assert result is None
    assert (wellness_dir / "2026-06-25.json").exists() is False


@pytest.mark.unit
def test_wellness_current_day_complete_saved(tmp_path: Path) -> None:
    """Current-day fetch with real sleep → saved and returned."""
    wellness_dir = tmp_path / "wellness"
    client = MagicMock()
    client.get_sleep_data.return_value = {"dailySleepDTO": {"sleepTimeSeconds": 22740}}
    client.get_hrv_data.return_value = None
    client.get_stats.return_value = None
    client.get_training_readiness.return_value = None

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_wellness_data(
            wellness_dir, "2026-06-25", today=date(2026, 6, 25)
        )

    assert result is not None
    assert (wellness_dir / "2026-06-25.json").exists()


@pytest.mark.unit
def test_wellness_past_day_partial_saved(tmp_path: Path) -> None:
    """Past-day partial fetch (no sleep) → saved (past-day keeps existing logic)."""
    wellness_dir = tmp_path / "wellness"
    client = MagicMock()
    client.get_sleep_data.return_value = None
    client.get_hrv_data.return_value = None
    client.get_stats.return_value = None
    client.get_training_readiness.return_value = {"score": 46}

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_wellness_data(
            wellness_dir, "2026-06-25", today=date(2026, 6, 26)
        )

    assert result is not None
    cache_file = wellness_dir / "2026-06-25.json"
    assert cache_file.exists()
    with open(cache_file, encoding="utf-8") as f:
        assert json.load(f) != {}


@pytest.mark.unit
def test_wellness_past_day_empty_writes_marker(tmp_path: Path) -> None:
    """Past-day fully empty fetch → empty marker written and None."""
    wellness_dir = tmp_path / "wellness"
    client = MagicMock()
    client.get_sleep_data.return_value = None
    client.get_hrv_data.return_value = None
    client.get_stats.return_value = None
    client.get_training_readiness.return_value = None

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_wellness_data(
            wellness_dir, "2026-06-25", today=date(2026, 6, 26)
        )

    assert result is None
    cache_file = wellness_dir / "2026-06-25.json"
    assert cache_file.exists()
    with open(cache_file, encoding="utf-8") as f:
        assert json.load(f) == {}
