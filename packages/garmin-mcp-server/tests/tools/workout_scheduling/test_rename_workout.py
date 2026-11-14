"""rename_workout: prefix rule, full-body PUT, no-op, error dict, readback (#1591)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools.workout_scheduling import (
    RenameWorkoutParams,
    _plan_rename,
    _rename_workout,
)

_CLIENT = "garmin_mcp.ingest.api_client.get_garmin_client"


def _workout(name: str) -> dict[str, Any]:
    return {
        "workoutId": 42,
        "workoutName": name,
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "workoutSteps": [{"stepOrder": 1, "endConditionValue": 600}],
            }
        ],
    }


@pytest.mark.unit
def test_plan_rename_keeps_mcp_prefix() -> None:
    assert _plan_rename("[MCP] Long 120min", "Long 100min") == "[MCP] Long 100min"
    assert _plan_rename("[MCP] A", "[MCP] B") == "[MCP] B"


@pytest.mark.unit
def test_plan_rename_manual_title_verbatim() -> None:
    assert _plan_rename("補強サーキット", " 体幹サーキット ") == "体幹サーキット"


@pytest.mark.unit
def test_plan_rename_rejects_mcp_prefix_on_manual() -> None:
    with pytest.raises(ValueError):
        _plan_rename("補強サーキット", "[MCP] x")


@pytest.mark.unit
def test_plan_rename_rejects_blank() -> None:
    with pytest.raises(ValueError):
        _plan_rename("[MCP] A", "  ")


@pytest.mark.unit
def test_rename_puts_full_body_with_new_name() -> None:
    client = MagicMock()
    original = _workout("[MCP] Long 120min")
    client.get_workout_by_id.side_effect = [original, _workout("[MCP] Long 100min")]

    with patch(_CLIENT, return_value=client):
        result = _rename_workout(
            MagicMock(), RenameWorkoutParams(workout_id=42, new_title="Long 100min")
        )

    client.update_workout.assert_called_once()
    workout_id, body = client.update_workout.call_args.args
    assert workout_id == 42
    assert body == {**original, "workoutName": "[MCP] Long 100min"}
    assert body["workoutSegments"] == original["workoutSegments"]
    assert result == {
        "workout_id": 42,
        "old_title": "[MCP] Long 120min",
        "new_title": "[MCP] Long 100min",
        "changed": True,
        "verified": True,
    }


@pytest.mark.unit
def test_rename_same_title_is_noop() -> None:
    client = MagicMock()
    client.get_workout_by_id.return_value = _workout("[MCP] Easy 40min")

    with patch(_CLIENT, return_value=client):
        result = _rename_workout(
            MagicMock(), RenameWorkoutParams(workout_id=42, new_title="Easy 40min")
        )

    client.update_workout.assert_not_called()
    assert result["changed"] is False


@pytest.mark.unit
def test_rename_handler_returns_error_dict() -> None:
    client = MagicMock()
    client.get_workout_by_id.side_effect = RuntimeError("API Error 404")

    with patch(_CLIENT, return_value=client):
        result = _rename_workout(
            MagicMock(), RenameWorkoutParams(workout_id=42, new_title="X")
        )

    assert "error" in result
    client.update_workout.assert_not_called()


@pytest.mark.unit
def test_rename_unverified_when_readback_differs() -> None:
    client = MagicMock()
    client.get_workout_by_id.side_effect = [
        _workout("[MCP] Long 120min"),
        _workout("[MCP] Long 120min"),
    ]

    with patch(_CLIENT, return_value=client):
        result = _rename_workout(
            MagicMock(), RenameWorkoutParams(workout_id=42, new_title="Long 100min")
        )

    assert result["changed"] is True
    assert result["verified"] is False
