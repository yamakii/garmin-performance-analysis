"""Tests for VO2 max collection in raw_data_fetcher (Issue #218).

`client.get_max_metrics()` returns a list of entries, but older raw dumps
stored a single dict. `_collect_vo2_max` must parse both shapes so the
`generic` metrics are extracted correctly instead of being silently dropped.
"""

import json
from unittest.mock import Mock

import pytest

from garmin_mcp.ingest.raw_data_fetcher import _collect_vo2_max


def _make_raw_data(date: str) -> dict:
    """Minimal raw_data with an activity date so date extraction succeeds."""
    return {
        "activity": {"summaryDTO": {"startTimeLocal": f"{date}T07:00:00.0"}},
    }


@pytest.mark.unit
def test_collect_vo2_max_parses_list_response(tmp_path):
    """get_max_metrics returning a list → generic metrics extracted and cached."""
    client = Mock()
    client.get_max_metrics.return_value = [
        {
            "generic": {
                "vo2MaxValue": 47.0,
                "vo2MaxPreciseValue": 47.3,
                "calendarDate": "2025-10-04",
            }
        }
    ]
    raw_data = _make_raw_data("2025-10-04")

    _collect_vo2_max(
        client,
        tmp_path,
        raw_data,
        activity_id=123,
        force_refetch_set=set(),
        fetch_status={},
    )

    expected = {
        "vo2MaxValue": 47.0,
        "vo2MaxPreciseValue": 47.3,
        "calendarDate": "2025-10-04",
    }
    assert raw_data["vo2_max"] == expected
    with open(tmp_path / "vo2_max.json", encoding="utf-8") as f:
        assert json.load(f) == expected


@pytest.mark.unit
def test_collect_vo2_max_parses_dict_response(tmp_path):
    """Legacy dict response (backward compat) → same extracted result."""
    client = Mock()
    client.get_max_metrics.return_value = {
        "generic": {
            "vo2MaxValue": 47.0,
            "vo2MaxPreciseValue": 47.3,
            "calendarDate": "2025-10-04",
        }
    }
    raw_data = _make_raw_data("2025-10-04")

    _collect_vo2_max(
        client,
        tmp_path,
        raw_data,
        activity_id=123,
        force_refetch_set=set(),
        fetch_status={},
    )

    expected = {
        "vo2MaxValue": 47.0,
        "vo2MaxPreciseValue": 47.3,
        "calendarDate": "2025-10-04",
    }
    assert raw_data["vo2_max"] == expected
    with open(tmp_path / "vo2_max.json", encoding="utf-8") as f:
        assert json.load(f) == expected


@pytest.mark.unit
def test_collect_vo2_max_empty_list(tmp_path):
    """Empty list response → empty {} cached, no exception raised."""
    client = Mock()
    client.get_max_metrics.return_value = []
    raw_data = _make_raw_data("2025-10-04")

    _collect_vo2_max(
        client,
        tmp_path,
        raw_data,
        activity_id=123,
        force_refetch_set=set(),
        fetch_status={},
    )

    assert raw_data["vo2_max"] == {}
    with open(tmp_path / "vo2_max.json", encoding="utf-8") as f:
        assert json.load(f) == {}
