"""Tests for GarminCalendarReader."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.training_plan.garmin_calendar import GarminCalendarReader


def _make_reader_with_calendar(
    mocker, calendar_by_path: dict[str, dict[str, Any]]
) -> tuple[GarminCalendarReader, Any]:
    """Build a reader whose client.client.connectapi returns path-specific dicts."""

    def connectapi(path: str) -> dict[str, Any]:
        return calendar_by_path.get(path, {"calendarItems": []})

    inner = mocker.MagicMock()
    inner.connectapi.side_effect = connectapi
    client = mocker.MagicMock()
    client.client = inner

    reader = GarminCalendarReader()
    mocker.patch.object(reader, "_get_garmin_client", return_value=client)
    return reader, inner


@pytest.mark.unit
class TestGarminCalendarReader:
    def test_get_scheduled_workouts_filters_types(self, mocker):
        """Only workout-type items (fbtAdaptiveWorkout/workout) are returned."""
        calendar = {
            "/calendar-service/year/2026/month/5": {
                "calendarItems": [
                    {
                        "date": "2026-06-16",
                        "title": "Tempo",
                        "itemType": "fbtAdaptiveWorkout",
                        "trainingPlanId": 99,
                        "trainingPlanName": "Adaptive",
                        "workoutUuid": "uuid-tempo",
                    },
                    {
                        "date": "2026-06-16",
                        "title": "Nap",
                        "itemType": "nap",
                    },
                    {
                        "date": "2026-06-17",
                        "title": "Weight",
                        "itemType": "weight",
                    },
                    {
                        "date": "2026-06-18",
                        "title": "Morning Run",
                        "itemType": "activity",
                    },
                    {
                        "date": "2026-06-19",
                        "title": "Base",
                        "itemType": "workout",
                        "workoutUuid": "uuid-base",
                    },
                ]
            }
        }
        reader, _ = _make_reader_with_calendar(mocker, calendar)

        result = reader.get_scheduled_workouts("2026-06-15", "2026-06-21")

        item_types = {r["item_type"] for r in result}
        assert item_types == {"fbtAdaptiveWorkout", "workout"}
        assert len(result) == 2
        first = result[0]
        assert first["date"] == "2026-06-16"
        assert first["title"] == "Tempo"
        assert first["training_plan_id"] == 99
        assert first["training_plan_name"] == "Adaptive"
        assert first["workout_uuid"] == "uuid-tempo"

    def test_get_scheduled_workouts_spans_months(self, mocker):
        """A range spanning two months fetches both 0-based months and merges."""
        calendar = {
            "/calendar-service/year/2026/month/5": {  # June (0-based 5)
                "calendarItems": [
                    {
                        "date": "2026-06-30",
                        "title": "June Base",
                        "itemType": "workout",
                    },
                ]
            },
            "/calendar-service/year/2026/month/6": {  # July (0-based 6)
                "calendarItems": [
                    {
                        "date": "2026-07-02",
                        "title": "July Tempo",
                        "itemType": "fbtAdaptiveWorkout",
                    },
                ]
            },
        }
        reader, inner = _make_reader_with_calendar(mocker, calendar)

        result = reader.get_scheduled_workouts("2026-06-29", "2026-07-05")

        called_paths = {call.args[0] for call in inner.connectapi.call_args_list}
        assert "/calendar-service/year/2026/month/5" in called_paths
        assert "/calendar-service/year/2026/month/6" in called_paths

        dates = [r["date"] for r in result]
        assert dates == ["2026-06-30", "2026-07-02"]

    def test_get_scheduled_workouts_date_filter(self, mocker):
        """Items outside [start, end] are excluded."""
        calendar = {
            "/calendar-service/year/2026/month/5": {
                "calendarItems": [
                    {
                        "date": "2026-06-14",  # before start
                        "title": "Too Early",
                        "itemType": "workout",
                    },
                    {
                        "date": "2026-06-18",  # in range
                        "title": "In Range",
                        "itemType": "workout",
                    },
                    {
                        "date": "2026-06-25",  # after end
                        "title": "Too Late",
                        "itemType": "workout",
                    },
                ]
            }
        }
        reader, _ = _make_reader_with_calendar(mocker, calendar)

        result = reader.get_scheduled_workouts("2026-06-15", "2026-06-21")

        assert len(result) == 1
        assert result[0]["date"] == "2026-06-18"
        assert result[0]["title"] == "In Range"


@pytest.mark.garmin_api
def test_get_scheduled_workouts_live():
    """Hits the real Garmin API (skipped in CI via garmin_api marker)."""
    reader = GarminCalendarReader()
    result = reader.get_scheduled_workouts("2026-06-15", "2026-06-21")
    assert isinstance(result, list)
    for item in result:
        assert "date" in item
        assert "item_type" in item
