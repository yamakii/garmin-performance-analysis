"""save_weekly_prescriptions authoring from catalog templates (Issue #1405).

A row's ``workout: {"template", "params"}`` is expanded by the tool into the
step structure (plus the title when the row has none) before the insert, and
registration then sends the repeat groups to the watch.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.plan import _expand_workout_rows
from garmin_mcp.tools.registry import dispatch
from garmin_mcp.tools.workout_scheduling import (
    ScheduleWeeklyPrescriptionsParams,
    _schedule_weekly_prescriptions,
)
from tests.support.schema import init_schema
from tests.tools.workout_scheduling._helpers import _CALENDAR, _offline_garmin

WEEK_START = "2026-11-02"
_DATE = "2026-11-04"
_CRUISE_TITLE = "クルーズ 4×5分（162-169）／3分ジョグ"


def _call(reader: MagicMock, name: str, arguments: dict[str, Any]) -> Any:
    return dispatch(ALL_DEFS_BY_NAME, reader, name, arguments)


@pytest.fixture(scope="module")
def _template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    db_path = tmp_path_factory.mktemp("plan_workout_templates") / "template.duckdb"
    init_schema(db_path)
    return Path(db_path)


@pytest.fixture
def reader(_template_db: Path, tmp_path: Path) -> MagicMock:
    dest = tmp_path / "plan_workout_templates.duckdb"
    shutil.copy2(str(_template_db), str(dest))
    mock = MagicMock()
    mock.db_path = dest
    return mock


def _cruise_row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": _DATE,
        "session_type": "threshold",
        "workout": {
            "template": "cruise_intervals",
            "params": {
                "reps": 4,
                "work_minutes": 5,
                "recovery_minutes": 3,
                "hr_low": 162,
                "hr_high": 169,
            },
        },
    }
    row.update(extra)
    return row


def _save(reader: MagicMock, rows: list[dict[str, Any]]) -> Any:
    return _call(
        reader,
        "save_weekly_prescriptions",
        {"week_start_date": WEEK_START, "prescriptions": rows},
    )


def _stored_rows(reader: MagicMock) -> list[dict[str, Any]]:
    result = _call(reader, "get_weekly_prescriptions", {"week_start_date": WEEK_START})
    assert isinstance(result, list)
    return result


def _groups(structure: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in structure if "repeat_count" in s]


@pytest.mark.integration
def test_save_expands_workout_template(reader: MagicMock) -> None:
    saved = _save(reader, [_cruise_row()])
    assert saved["status"] == "saved", saved

    (row,) = _stored_rows(reader)
    assert row["title"] == _CRUISE_TITLE
    assert row["purpose"] == "intervals"
    (group,) = _groups(row["structure"])
    assert group["repeat_count"] == 4
    work = group["steps"][0]
    assert work["hr_low"] == 162
    assert work["hr_high"] == 169
    # threshold rows derive the body only: 4 x (5 + 3) minutes.
    assert row["target_minutes"] == 32


@pytest.mark.integration
def test_save_keeps_explicit_title(reader: MagicMock) -> None:
    saved = _save(reader, [_cruise_row(title="閾値クルーズ")])
    assert saved["status"] == "saved", saved

    (row,) = _stored_rows(reader)
    assert row["title"] == "閾値クルーズ"
    assert _groups(row["structure"])[0]["repeat_count"] == 4


@pytest.mark.integration
def test_save_rejects_workout_with_structure(reader: MagicMock) -> None:
    both = _cruise_row(
        structure=[{"step_type": "run", "duration_minutes": 20, "hr_high": 169}]
    )
    with pytest.raises(ValueError, match=_DATE):
        _expand_workout_rows([both])

    result = _save(reader, [both])
    assert "error" in result
    assert _DATE in result["error"]
    assert _stored_rows(reader) == []


@pytest.mark.integration
def test_save_rejects_unknown_template(reader: MagicMock) -> None:
    row = _cruise_row(workout={"template": "foo", "params": {}})
    with pytest.raises(ValueError, match="unknown workout template"):
        _expand_workout_rows([row])

    result = _save(reader, [row])
    assert "unknown workout template" in result["error"]
    assert _stored_rows(reader) == []


@pytest.mark.integration
def test_schedule_dry_run_registers_repeat_group(reader: MagicMock) -> None:
    saved = _save(reader, [_cruise_row()])
    assert saved["status"] == "saved", saved

    calendar = MagicMock()
    calendar.return_value.get_scheduled_workouts.return_value = []
    with patch(_CALENDAR, calendar), _offline_garmin():
        result = _schedule_weekly_prescriptions(
            reader, ScheduleWeeklyPrescriptionsParams(week_start_date=WEEK_START)
        )

    (item,) = result["items"]
    steps = item["steps"]
    (group,) = _groups(steps)
    assert group["repeat_count"] == 4
    work = group["steps"][0]
    assert work["step_type"] == "run"
    assert (work["hr_low"], work["hr_high"]) == (162, 169)

    def _keys(step_list: list[dict[str, Any]]) -> set[str]:
        keys: set[str] = set()
        for step in step_list:
            keys |= set(step)
            keys |= _keys(step.get("steps", []))
        return keys

    assert not any(k.startswith("pace") for k in _keys(steps))
