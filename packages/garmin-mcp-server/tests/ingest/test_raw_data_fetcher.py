"""Tests for per-API fetch_status tracking in collect_data (Issue #704).

`collect_data` records the per-API outcome ("fetched" | "cached" | "marker" |
"failed") in the returned ``fetch_status`` dict so partial failures become
visible instead of silently passing as "success".
"""

import os
from datetime import date as dt_date
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from garmin_mcp.ingest.raw_data_fetcher import (
    _collect_vo2_max,
    _marker_is_authoritative,
    collect_body_composition_data,
    collect_data,
    collect_wellness_data,
)


def _set_mtime(path, iso_datetime: str) -> None:
    """Set a file's mtime to the given ISO datetime (used for marker aging)."""
    ts = datetime.fromisoformat(iso_datetime).timestamp()
    os.utime(path, (ts, ts))


def _mock_client():
    """Mock Garmin client whose endpoints all return usable payloads."""

    client = Mock()
    client.get_activity.return_value = {
        "activityId": 123,
        "summaryDTO": {
            "duration": 1800,
            "startTimeLocal": "2025-10-04T07:00:00.0",
            "trainingEffect": 3.0,
        },
    }
    client.get_activity_details.return_value = {"activityId": 123}
    client.get_activity_splits.return_value = {"lapDTOs": [], "eventDTOs": []}
    client.get_activity_weather.return_value = {"temp": 18}
    client.get_activity_gear.return_value = []
    client.get_activity_hr_in_timezones.return_value = []
    client.get_max_metrics.return_value = [
        {
            "generic": {
                "vo2MaxValue": 47.0,
                "vo2MaxPreciseValue": 47.3,
                "calendarDate": "2025-10-04",
            }
        }
    ]
    client.get_lactate_threshold.return_value = {"lactateThresholdBPM": 160}
    return client


@pytest.mark.unit
def test_collect_data_reports_fetched_status(tmp_path):
    """All APIs succeed on cache miss → every fetch_status entry is fetched."""
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=_mock_client(),
    ):
        result = collect_data(tmp_path, activity_id=123)

    fetch_status = result["fetch_status"]
    # No cache existed, so every tracked API was freshly fetched.
    assert set(fetch_status.values()) <= {"fetched", "cached"}
    for key in (
        "activity_basic",
        "activity_details",
        "splits",
        "weather",
        "gear",
        "hr_zones",
        "vo2_max",
        "lactate_threshold",
    ):
        assert fetch_status[key] in {"fetched", "cached"}


@pytest.mark.unit
def test_collect_data_marks_failed_on_api_error(tmp_path):
    """weather API raising → fetch_status[weather]=="failed" and value is None."""
    client = _mock_client()
    client.get_activity_weather.side_effect = RuntimeError("weather API down")

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_data(tmp_path, activity_id=123)

    assert result["fetch_status"]["weather"] == "failed"
    assert result["weather"] is None


@pytest.mark.unit
def test_collect_data_marks_marker_for_empty_vo2(tmp_path):
    """VO2 response without 'generic' metrics → fetch_status[vo2_max]=="marker"."""
    client = _mock_client()
    client.get_max_metrics.return_value = []  # no generic metrics available

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        result = collect_data(tmp_path, activity_id=123)

    assert result["fetch_status"]["vo2_max"] == "marker"
    assert result["vo2_max"] == {}


# --- Issue #705: empty-marker self-heal -------------------------------------


@pytest.mark.unit
def test_stale_marker_refetched_within_grace(tmp_path):
    """Marker written 1 day after target (within grace) → not authoritative."""
    marker = tmp_path / "2026-06-30.json"
    marker.write_text("{}")
    _set_mtime(marker, "2026-07-01")  # 1 day after target, well within 7d grace

    assert _marker_is_authoritative(marker, "2026-06-30", grace_days=7) is False


@pytest.mark.unit
def test_authoritative_marker_skips_fetch(tmp_path):
    """Marker written 19 days after target (past grace) → authoritative."""
    marker = tmp_path / "2026-06-01.json"
    marker.write_text("{}")
    _set_mtime(marker, "2026-06-20")  # 19 days after target, past 7d grace

    assert _marker_is_authoritative(marker, "2026-06-01", grace_days=7) is True


@pytest.mark.unit
def test_weight_error_does_not_write_marker(tmp_path):
    """weight API raising → no marker file is written (self-heal next run)."""
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        side_effect=RuntimeError("weight API down"),
    ):
        result = collect_body_composition_data(
            tmp_path, "2026-06-01", today=dt_date(2026, 7, 2)
        )

    assert result is None
    assert not (tmp_path / "2026-06-01.json").exists()


@pytest.mark.unit
def test_wellness_error_does_not_write_marker(tmp_path):
    """wellness API raising → no marker file is written (self-heal next run)."""
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        side_effect=RuntimeError("wellness API down"),
    ):
        result = collect_wellness_data(
            tmp_path, "2026-06-01", today=dt_date(2026, 7, 2)
        )

    assert result is None
    assert not (tmp_path / "2026-06-01.json").exists()


@pytest.mark.unit
def test_vo2_empty_marker_refetched_within_grace(tmp_path):
    """Stale ``{}`` vo2_max marker (written day after target) → re-fetch runs."""
    activity_date = "2026-06-30"
    activity_dir = tmp_path / "activity" / "123"
    activity_dir.mkdir(parents=True)
    vo2_file = activity_dir / "vo2_max.json"
    vo2_file.write_text("{}")
    _set_mtime(vo2_file, "2026-07-01")  # 1 day after target → not authoritative

    client = _mock_client()  # get_max_metrics returns real VO2 metrics
    raw_data = {
        "activity_basic": {
            "summaryDTO": {"startTimeLocal": f"{activity_date}T07:00:00.0"}
        }
    }
    fetch_status: dict = {}

    _collect_vo2_max(
        client,
        activity_dir,
        raw_data,
        activity_id=123,
        force_refetch_set=set(),
        fetch_status=fetch_status,
    )

    client.get_max_metrics.assert_called_once_with(activity_date)
    assert fetch_status["vo2_max"] == "fetched"
    assert raw_data["vo2_max"]["vo2MaxValue"] == 47.0


@pytest.mark.integration
def test_wellness_self_heal_e2e(tmp_path):
    """1st fetch fails (no marker) → 2nd fetch succeeds and caches data."""
    date = "2026-06-01"
    today = dt_date(2026, 7, 2)

    # 1st run: API raises → no marker, returns None.
    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        side_effect=RuntimeError("transient outage"),
    ):
        first = collect_wellness_data(tmp_path, date, today=today)
    assert first is None
    assert not (tmp_path / f"{date}.json").exists()

    # 2nd run: API succeeds → data merged, cached, and returned.
    client = Mock()
    client.get_stats.return_value = {"restingHeartRate": 48}
    client.get_hrv_data.return_value = {"hrvSummary": {"lastNightAvg": 60}}
    client.get_sleep_data.return_value = {"dailySleepDTO": {"sleepTimeSeconds": 25200}}
    client.get_training_readiness.return_value = [{"score": 70}]

    with patch(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        return_value=client,
    ):
        second = collect_wellness_data(tmp_path, date, today=today)

    assert second is not None
    assert second["stats"]["restingHeartRate"] == 48
    assert (tmp_path / f"{date}.json").exists()
