"""Similar workouts carry their comparability with the target (#1523)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from garmin_mcp.rag.queries.comparisons import WorkoutComparator

_TARGET = 15230001
_POD = 15230002
_WRIST = 15230003
_LOADED = 15230004

_TARGET_ROWS = [(_TARGET, "2026-10-20", "Run", 400.0, 140.0, 8.0)]
_CANDIDATE_ROWS = [
    (_POD, "2026-10-18", "Run", 402.0, 141.0, 8.0),
    (_WRIST, "2026-10-16", "Run", 405.0, 139.0, 8.1),
    (_LOADED, "2026-10-14", "Run", 410.0, 145.0, 7.9),
]
_PROFILES: dict[int, dict[str, Any]] = {
    _TARGET: {"dynamics_source": "pod", "hr_source": "chest_strap", "load_kg": None},
    _POD: {"dynamics_source": "pod", "hr_source": "chest_strap", "load_kg": None},
    _WRIST: {"dynamics_source": "wrist", "hr_source": "chest_strap", "load_kg": None},
    _LOADED: {"dynamics_source": "pod", "hr_source": "chest_strap", "load_kg": 3.0},
}


@pytest.fixture
def comparator() -> Iterator[WorkoutComparator]:
    with patch("garmin_mcp.rag.queries.comparisons.GarminDBReader") as mock_reader:
        comparator = WorkoutComparator()
        comparator.db_reader = mock_reader.return_value
        comparator.db_reader.get_weather_data.return_value = None  # type: ignore[attr-defined]
        comparator.db_reader.get_hr_efficiency_analysis.return_value = {  # type: ignore[attr-defined]
            "training_type": "aerobic_base"
        }
        yield comparator


def _find(comparator: WorkoutComparator, **kwargs: Any) -> dict[str, Any]:
    with (
        patch.object(
            comparator,
            "_execute_query",
            side_effect=[_TARGET_ROWS, _CANDIDATE_ROWS],
        ),
        patch.object(comparator, "_load_profiles", return_value=_PROFILES),
    ):
        return comparator.find_similar_workouts(_TARGET, **kwargs)


@pytest.mark.unit
def test_find_similar_workouts_annotates_comparability(
    comparator: WorkoutComparator,
) -> None:
    result = _find(comparator)

    by_id = {item["activity_id"]: item for item in result["similar_activities"]}
    assert set(by_id) == {_POD, _WRIST, _LOADED}
    assert by_id[_POD]["comparability"]["reasons"] == []
    assert by_id[_WRIST]["comparability"]["reasons"] == ["dynamics_source_differs"]
    assert by_id[_LOADED]["comparability"]["reasons"] == ["load_differs"]
    assert "gct_ms" in by_id[_WRIST]["comparability"]["excluded_metrics"]


@pytest.mark.unit
def test_find_similar_workouts_same_sensor_only_filters(
    comparator: WorkoutComparator,
) -> None:
    result = _find(comparator, same_sensor_only=True)

    ids = [item["activity_id"] for item in result["similar_activities"]]
    # The wrist run goes; a load is not a sensor, so the loaded run stays
    # (annotated).
    assert ids == [_POD, _LOADED]
