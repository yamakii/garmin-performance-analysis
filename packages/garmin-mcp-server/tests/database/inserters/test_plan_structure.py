"""Tests for the prescription step ``structure`` (Issue #1401, Epic #1398).

Covers how ``insert_weekly_prescriptions`` validates and stores a row's step
structure (bpm only, never together with ``strides``), the ``target_minutes``
it derives from a fully timed structure (body only for threshold / tempo, the
total otherwise, never the HR bounds), ``update_prescription_status`` recording
the steps of a hand-built registration, and legacy rows reading back ``None``.

Split out of ``test_plan.py`` to keep both files under the test-size budget.
Uses the module-scoped ``initialized_db_path`` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.inserters.plan import (
    insert_weekly_prescriptions,
    update_prescription_status,
)

#: WU 10 min, a 20-min body at 162-169 bpm, CD 5 min.
_TEMPO_STRUCTURE: list[dict[str, Any]] = [
    {"step_type": "warmup", "duration_minutes": 10},
    {"step_type": "run", "duration_minutes": 20, "hr_low": 162, "hr_high": 169},
    {"step_type": "cooldown", "duration_minutes": 5},
]


def _prescription(
    on_date: str, session_type: str = "easy", **overrides: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": on_date,
        "session_type": session_type,
        "title": f"{session_type} {on_date}",
        "target_minutes": 50,
        "target_km": None,
        "hr_low": None,
        "hr_high": 141,
        "rationale": "有酸素維持",
    }
    row.update(overrides)
    return row


def _read_week(db_path: str) -> list[dict[str, Any]]:
    """Read the canonical rows of the 2026-09-07 week through the reader."""
    from garmin_mcp.database.readers.plan import PlanReader

    rows: list[dict[str, Any]] = PlanReader(db_path=db_path).get_weekly_prescriptions(
        "2026-09-07"
    )
    return rows


@pytest.mark.integration
def test_insert_prescription_with_structure_roundtrip(
    initialized_db_path: Path,
) -> None:
    """A tempo row's structure reads back as an equal list."""
    db_path = str(initialized_db_path)
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription(
                "2026-09-10",
                "tempo",
                target_minutes=20,
                hr_high=None,
                structure=_TEMPO_STRUCTURE,
            )
        ],
        db_path=db_path,
    )

    rows = _read_week(db_path)
    assert rows[0]["structure"] == _TEMPO_STRUCTURE


@pytest.mark.integration
def test_insert_rejects_strides_and_structure(initialized_db_path: Path) -> None:
    """An easy row cannot carry both a strides add-on and a structure."""
    structure = [{"step_type": "run", "duration_minutes": 60, "hr_high": 141}]
    with pytest.raises(ValueError, match="either strides or structure"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [
                _prescription(
                    "2026-09-09",
                    target_minutes=60,
                    strides={"reps": 4},
                    structure=structure,
                )
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.integration
def test_insert_rejects_zone_label(initialized_db_path: Path) -> None:
    """A structure step's HR must be bpm, never a zone label like "Z4"."""
    structure = [
        {"step_type": "warmup", "duration_minutes": 10},
        {"step_type": "run", "duration_minutes": 20, "hr_high": "Z4"},
        {"step_type": "cooldown", "duration_minutes": 5},
    ]
    with pytest.raises(ValueError, match="hr_high must be an integer bpm"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [
                _prescription(
                    "2026-09-10",
                    "tempo",
                    target_minutes=None,
                    hr_high=None,
                    structure=structure,
                )
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.integration
def test_insert_derives_body_minutes_for_threshold(
    initialized_db_path: Path,
) -> None:
    """A threshold row without target_minutes stores the body (20), not 35."""
    db_path = str(initialized_db_path)
    structure = [
        {"step_type": "warmup", "duration_minutes": 10},
        {"step_type": "run", "duration_minutes": 20},
        {"step_type": "cooldown", "duration_minutes": 5},
    ]
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription(
                "2026-09-10",
                "threshold",
                target_minutes=None,
                hr_high=None,
                structure=structure,
            )
        ],
        db_path=db_path,
    )

    rows = _read_week(db_path)
    assert rows[0]["target_minutes"] == 20


@pytest.mark.integration
def test_insert_derives_total_minutes_for_easy(initialized_db_path: Path) -> None:
    """A non-bookended row derives target_minutes as the structure total."""
    db_path = str(initialized_db_path)
    structure = [
        {"step_type": "run", "duration_minutes": 40, "hr_high": 141},
        {
            "repeat_count": 4,
            "steps": [
                {"step_type": "run", "duration_seconds": 20},
                {"step_type": "recovery", "duration_seconds": 100},
            ],
        },
        {"step_type": "cooldown", "duration_minutes": 5},
    ]
    insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-09", target_minutes=None, structure=structure)],
        db_path=db_path,
    )

    rows = _read_week(db_path)
    # 40 min + 4 x 2 min + 5 min.
    assert rows[0]["target_minutes"] == 53


@pytest.mark.integration
def test_insert_does_not_derive_hr_bounds(initialized_db_path: Path) -> None:
    """A build-up with per-stage bands leaves the row's hr_low / hr_high NULL."""
    db_path = str(initialized_db_path)
    structure = [
        {"step_type": "run", "duration_minutes": 40, "hr_low": 130, "hr_high": 140},
        {"step_type": "run", "duration_minutes": 30, "hr_low": 140, "hr_high": 150},
        {"step_type": "run", "duration_minutes": 20, "hr_low": 150, "hr_high": 160},
    ]
    insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription(
                "2026-09-13",
                "long",
                target_minutes=None,
                hr_low=None,
                hr_high=None,
                structure=structure,
            )
        ],
        db_path=db_path,
    )

    rows = _read_week(db_path)
    assert rows[0]["hr_low"] is None
    assert rows[0]["hr_high"] is None
    assert rows[0]["target_minutes"] == 90


@pytest.mark.integration
def test_insert_rejects_structure_on_rest_row(initialized_db_path: Path) -> None:
    """A structure only makes sense on a session that runs."""
    structure = [{"step_type": "run", "duration_minutes": 30}]
    with pytest.raises(ValueError, match="only be set on a run session"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [
                _prescription(
                    "2026-09-11",
                    "rest",
                    target_minutes=None,
                    hr_high=None,
                    structure=structure,
                )
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.integration
def test_update_prescription_status_records_structure(
    initialized_db_path: Path,
) -> None:
    """Registering with a structure stores it; a later update keeps it."""
    db_path = str(initialized_db_path)
    saved = insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-10", "tempo", target_minutes=20, hr_high=None)],
        db_path=db_path,
    )
    prescription_id = saved["prescription_ids"][0]

    def _stored() -> Any:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT structure FROM weekly_prescriptions WHERE prescription_id = ?",
                [prescription_id],
            ).fetchone()
        assert row is not None
        return json.loads(row[0]) if row[0] is not None else None

    assert _stored() is None

    update_prescription_status(
        prescription_id,
        "registered",
        garmin_workout_id=321,
        structure=_TEMPO_STRUCTURE,
        db_path=db_path,
    )
    assert _stored() == _TEMPO_STRUCTURE

    update_prescription_status(
        prescription_id, "done", actual_activity_id=999, db_path=db_path
    )
    assert _stored() == _TEMPO_STRUCTURE


@pytest.mark.unit
def test_update_prescription_status_rejects_invalid_structure() -> None:
    """An invalid structure is rejected before touching the DB."""
    with pytest.raises(ValueError, match="hr_high must be an integer bpm"):
        update_prescription_status(
            1,
            "registered",
            structure=[{"step_type": "run", "duration_minutes": 20, "hr_high": "Z4"}],
            db_path="/nonexistent/never-opened.duckdb",
        )


@pytest.mark.integration
def test_legacy_rows_read_structure_null(initialized_db_path: Path) -> None:
    """A row saved without a structure reads back None, other fields unchanged."""
    db_path = str(initialized_db_path)
    insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-09", purpose="easy")],
        db_path=db_path,
    )

    rows = _read_week(db_path)
    assert rows[0]["structure"] is None
    assert rows[0]["target_minutes"] == 50
    assert rows[0]["hr_high"] == 141
    assert rows[0]["purpose"] == "easy"
    assert rows[0]["strides"] is None
