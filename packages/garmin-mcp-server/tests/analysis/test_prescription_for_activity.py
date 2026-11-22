"""Which run of a multi-run day answers the day's prescription (#1601)."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.derivations import prescription_for_activity
from garmin_mcp.analysis.prescription_reconcile import answering_activity_id

_LONG = 101
_COOLDOWN = 102


def _long_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "session_type": "long",
        "target_km": 28.0,
        "target_minutes": None,
        "actual_activity_id": None,
    }
    row.update(overrides)
    return row


def _run(activity_id: int, km: float, minutes: float) -> dict[str, Any]:
    return {"activity_id": activity_id, "distance_km": km, "duration_min": minutes}


_DAY = [_run(_LONG, 28.0, 188.0), _run(_COOLDOWN, 0.8, 6.5)]


@pytest.mark.unit
def test_answering_activity_id_uses_linked_activity() -> None:
    row = _long_row(actual_activity_id=7)
    assert answering_activity_id(row, [_run(5, 10.0, 60), _run(7, 5.0, 30)]) == 7


@pytest.mark.unit
def test_answering_activity_id_picks_in_tolerance_run() -> None:
    assert answering_activity_id(_long_row(), _DAY) == _LONG


@pytest.mark.unit
def test_answering_activity_id_none_without_runs() -> None:
    assert answering_activity_id(_long_row(), []) is None


@pytest.mark.unit
def test_prescription_for_activity_drops_row_for_other_run() -> None:
    row = _long_row()
    assert prescription_for_activity([row], _COOLDOWN, _DAY) is None
    assert prescription_for_activity([row], _LONG, _DAY) is row


@pytest.mark.unit
def test_prescription_for_activity_single_run_unchanged() -> None:
    row = _long_row()
    one_short_run = [_run(_COOLDOWN, 0.8, 6.5)]
    assert prescription_for_activity([row], _COOLDOWN, one_short_run) is row
    assert prescription_for_activity([row], _COOLDOWN, None) is row


@pytest.mark.unit
def test_prescription_for_activity_no_rows() -> None:
    assert prescription_for_activity([], _LONG, _DAY) is None
