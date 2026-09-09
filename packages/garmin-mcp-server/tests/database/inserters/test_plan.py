"""Tests for the training plan ledger inserters.

Covers the 洗い替え + snapshot semantics of ``insert_training_blocks``, the
one-batch-per-save semantics of ``insert_weekly_prescriptions``, the mutable
status path (``update_prescription_status``), and the validation that keeps a
malformed plan out of the ledger.

Uses the module-scoped ``initialized_db_path`` fixture (schema pre-initialized
via file copy) to avoid per-test GarminDBWriter DDL overhead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.inserters.plan import (
    insert_training_blocks,
    insert_weekly_prescriptions,
    update_prescription_status,
)


def _block(title: str, start: str, end: str, **overrides: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "phase": "build",
        "title": title,
        "start_date": start,
        "end_date": end,
        "purpose": "ロング階段で脚の耐久性を伸ばす",
        "weight_mode": "維持",
        "quality_sessions_per_week": 1,
        "quality_types": ["threshold_cruise", "strides"],
        "long_run_ladder": [
            {
                "week_start": "2026-09-07",
                "target_km": 22.0,
                "target_minutes": None,
                "hr_ceiling": 150,
                "kind": "build",
                "note": "ラダー2段目",
            }
        ],
        "cutback_rule": {
            "trigger": "long_run_streak>=3",
            "long_run_pct": -35,
            "volume_pct": -25,
        },
        "notes": None,
    }
    block.update(overrides)
    return block


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


@pytest.mark.unit
def test_insert_training_blocks_replaces_and_snapshots(
    initialized_db_path: Path,
) -> None:
    """Saving replaces the canonical rows wholesale and appends a snapshot."""
    db_path = str(initialized_db_path)

    first = insert_training_blocks(
        [
            _block("新潟ラダー", "2026-08-24", "2026-09-20"),
            _block("テーパー", "2026-09-21", "2026-10-11", phase="taper"),
        ],
        db_path=db_path,
    )
    assert first["count"] == 2

    second = insert_training_blocks(
        [_block("新潟ラダー (改)", "2026-08-24", "2026-09-20")],
        db_path=db_path,
    )
    assert second["count"] == 1
    assert second["version_id"] > first["version_id"]

    with get_connection(db_path) as conn:
        blocks = conn.execute(
            "SELECT title, sequence FROM training_blocks ORDER BY sequence"
        ).fetchall()
        versions = conn.execute(
            "SELECT blocks_data FROM training_block_versions " "ORDER BY version_id"
        ).fetchall()

    assert blocks == [("新潟ラダー (改)", 1)]
    assert len(versions) == 2
    assert len(json.loads(versions[0][0])) == 2
    assert len(json.loads(versions[1][0])) == 1


@pytest.mark.unit
def test_insert_training_blocks_rejects_end_before_start(
    initialized_db_path: Path,
) -> None:
    """An inverted date range is rejected before anything is written."""
    with pytest.raises(ValueError, match="after end_date"):
        insert_training_blocks(
            [_block("逆転ブロック", "2026-09-07", "2026-09-01")],
            db_path=str(initialized_db_path),
        )

    with get_connection(str(initialized_db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM training_blocks").fetchone()
    assert row is not None
    assert row[0] == 0


@pytest.mark.unit
def test_insert_training_blocks_rejects_ladder_step_without_target(
    initialized_db_path: Path,
) -> None:
    """A ladder step with neither target_km nor target_minutes is rejected."""
    with pytest.raises(ValueError, match="exactly one of target_km"):
        insert_training_blocks(
            [
                _block(
                    "無目標ラダー",
                    "2026-08-24",
                    "2026-09-20",
                    long_run_ladder=[{"week_start": "2026-09-07"}],
                )
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_insert_weekly_prescriptions_assigns_one_batch_id(
    initialized_db_path: Path,
) -> None:
    """All rows of one save share a batch_id; every new id is returned."""
    result = insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription("2026-09-08"),
            _prescription("2026-09-10", "threshold", hr_low=160, hr_high=169),
            _prescription("2026-09-13", "long", target_km=25.0, target_minutes=None),
        ],
        db_path=str(initialized_db_path),
    )

    assert result["count"] == 3
    assert len(result["prescription_ids"]) == 3

    with get_connection(str(initialized_db_path)) as conn:
        batches = conn.execute(
            "SELECT DISTINCT batch_id FROM weekly_prescriptions"
        ).fetchall()
        statuses = conn.execute(
            "SELECT DISTINCT status FROM weekly_prescriptions"
        ).fetchall()

    assert batches == [(result["batch_id"],)]
    assert statuses == [("prescribed",)]


@pytest.mark.unit
def test_insert_weekly_prescriptions_rejects_date_outside_week(
    initialized_db_path: Path,
) -> None:
    """A row dated in the following week is rejected."""
    with pytest.raises(ValueError, match="outside the week"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-14")],
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_insert_weekly_prescriptions_rejects_hr_low_above_high(
    initialized_db_path: Path,
) -> None:
    """An inverted HR band is rejected."""
    with pytest.raises(ValueError, match="hr_low 160 is above hr_high 150"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09", hr_low=160, hr_high=150)],
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
@pytest.mark.parametrize("session_type", ["tempo", "threshold"])
def test_insert_prescriptions_rejects_bookended_target_minutes_as_total(
    initialized_db_path: Path, session_type: str
) -> None:
    """A quality row whose target_minutes is the session total is rejected (#1084).

    55min + 15min of bookends over 8.0km implies 8:45/km for a Z3-Z4 session,
    which only happens when the body-only convention was ignored.
    """
    with pytest.raises(ValueError, match="8:45/km"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [
                _prescription(
                    "2026-09-09",
                    session_type=session_type,
                    target_minutes=55,
                    target_km=8.0,
                    hr_low=162,
                    hr_high=169,
                )
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_insert_prescriptions_accepts_bookended_body_only_minutes(
    initialized_db_path: Path,
) -> None:
    """The same row written to convention (body minutes) is accepted (#1084)."""
    result = insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription(
                "2026-09-09",
                session_type="tempo",
                target_minutes=31,
                target_km=8.0,
                hr_low=162,
                hr_high=169,
            )
        ],
        db_path=str(initialized_db_path),
    )
    assert result["count"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("session_type", "target_minutes", "target_km"),
    [
        ("easy", 55, 8.0),
        ("long", 55, 8.0),
        ("recovery", 55, 8.0),
        ("tempo", 55, None),
        ("tempo", None, 8.0),
        ("tempo", None, None),
    ],
)
def test_insert_prescriptions_bookend_guard_leaves_other_rows_alone(
    initialized_db_path: Path,
    session_type: str,
    target_minutes: int | None,
    target_km: float | None,
) -> None:
    """Non-bookended types and half-specified rows are out of the guard's scope.

    easy / long / recovery prescribe the total in target_minutes by convention,
    and a row missing either target gives the check no basis to compare (#1084).
    """
    result = insert_weekly_prescriptions(
        "2026-09-07",
        [
            _prescription(
                "2026-09-09",
                session_type=session_type,
                target_minutes=target_minutes,
                target_km=target_km,
            )
        ],
        db_path=str(initialized_db_path),
    )
    assert result["count"] == 1


def _save_review(db_path: str, week_start_date: str = "2026-09-07") -> int:
    """Save a bare weekly review for a week and return its review_id."""
    from garmin_mcp.database.inserters.athlete import insert_weekly_review

    review = {
        "user_id": "default",
        "week_start_date": week_start_date,
        "week_end_date": "2026-09-13",
        "review_date": "2026-09-07",
        "review_data": {"overall": "順調"},
        "agent_name": "weekly-review",
        "agent_version": "1.0",
    }
    return int(insert_weekly_review(review, db_path=db_path))


@pytest.mark.unit
def test_insert_prescriptions_stores_rating(initialized_db_path: Path) -> None:
    """The coach verdict is stored on the prescription row (#1021)."""
    db_path = str(initialized_db_path)
    insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-10", "threshold", rating="🟡")],
        db_path=db_path,
    )

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT rating FROM weekly_prescriptions").fetchone()

    assert row is not None
    assert row[0] == "🟡"


@pytest.mark.unit
def test_insert_prescriptions_rejects_unknown_rating(
    initialized_db_path: Path,
) -> None:
    """A rating outside ✅ / 🟡 / 🔴 is rejected."""
    with pytest.raises(ValueError, match="rating must be one of"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09", rating="★")],
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_insert_prescriptions_rejects_second_batch_for_same_review(
    initialized_db_path: Path,
) -> None:
    """A revision must pair with a new review version, not a second batch."""
    db_path = str(initialized_db_path)
    review_id = _save_review(db_path)
    insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-09")],
        review_id=review_id,
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="new review version"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09", title="Z2 25分")],
            review_id=review_id,
            db_path=db_path,
        )


@pytest.mark.unit
def test_insert_prescriptions_requires_latest_review_id(
    initialized_db_path: Path,
) -> None:
    """Once a week has reviews, the batch must carry the latest review_id."""
    db_path = str(initialized_db_path)
    first_review_id = _save_review(db_path)
    _save_review(db_path)

    with pytest.raises(ValueError, match="is not the latest review"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09")],
            review_id=first_review_id,
            db_path=db_path,
        )

    with pytest.raises(ValueError, match="already has a weekly review"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09")],
            db_path=db_path,
        )


@pytest.mark.unit
def test_insert_prescriptions_rejects_unknown_review_id(
    initialized_db_path: Path,
) -> None:
    """A review_id that does not exist is rejected before anything is written."""
    with pytest.raises(ValueError, match="does not exist"):
        insert_weekly_prescriptions(
            "2026-09-07",
            [_prescription("2026-09-09")],
            review_id=999,
            db_path=str(initialized_db_path),
        )


@pytest.mark.unit
def test_insert_prescriptions_without_review_allowed(
    initialized_db_path: Path,
) -> None:
    """A week without any review still accepts an unlinked batch."""
    result = insert_weekly_prescriptions(
        "2026-09-07",
        [_prescription("2026-09-09")],
        db_path=str(initialized_db_path),
    )

    assert result["batch_id"] > 0
    assert result["count"] == 1


@pytest.mark.unit
def test_update_prescription_status_sets_ids_and_updated_at(
    initialized_db_path: Path,
) -> None:
    """Status + both Garmin ids are written and updated_at is refreshed."""
    db_path = str(initialized_db_path)
    saved = insert_weekly_prescriptions(
        "2026-09-07", [_prescription("2026-09-10", "threshold")], db_path=db_path
    )
    prescription_id = saved["prescription_ids"][0]

    assert (
        update_prescription_status(
            prescription_id,
            "registered",
            garmin_workout_id=123,
            garmin_schedule_id=456,
            db_path=db_path,
        )
        is True
    )

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status, garmin_workout_id, garmin_schedule_id, "
            "actual_activity_id, updated_at FROM weekly_prescriptions "
            "WHERE prescription_id = ?",
            [prescription_id],
        ).fetchone()

    assert row is not None
    assert row[0] == "registered"
    assert row[1] == 123
    assert row[2] == 456
    assert row[3] is None
    assert row[4] is not None


@pytest.mark.unit
def test_update_prescription_status_unknown_id_returns_false(
    initialized_db_path: Path,
) -> None:
    """Updating a non-existent id reports failure instead of raising."""
    assert (
        update_prescription_status(9999, "done", db_path=str(initialized_db_path))
        is False
    )


@pytest.mark.unit
def test_update_prescription_status_rejects_unknown_status() -> None:
    """An unknown lifecycle state raises before touching the database."""
    with pytest.raises(ValueError, match="status must be one of"):
        update_prescription_status(1, "maybe", db_path="unused.duckdb")
