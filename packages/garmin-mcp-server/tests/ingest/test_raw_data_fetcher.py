"""Tests for per-API fetch_status tracking in collect_data (Issue #704).

`collect_data` records the per-API outcome ("fetched" | "cached" | "marker" |
"failed") in the returned ``fetch_status`` dict so partial failures become
visible instead of silently passing as "success".
"""

from unittest.mock import patch

import pytest

from garmin_mcp.ingest.raw_data_fetcher import collect_data


def _mock_client():
    """Mock Garmin client whose endpoints all return usable payloads."""
    from unittest.mock import Mock

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
