"""Write gate: prose that reaches the web app carries no emoji (Issue #1428).

Every store the web renders prose from refuses a payload with emoji before it
writes anything, so a regression shows up at save time instead of on a page.
The verdict ``rating`` key (✅ / 🟡 / 🔴) is data, not prose, and stays allowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.database.connection import get_connection
from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.athlete import (
    insert_athlete_profile,
    insert_symptom,
    insert_weekly_review,
)
from garmin_mcp.database.inserters.plan import (
    insert_training_blocks,
    insert_weekly_prescriptions,
)
from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis


def _count(db_path: str, table: str) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    return int(row[0]) if row is not None else 0


def _review(review_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": "default",
        "week_start_date": "2026-09-21",
        "week_end_date": "2026-09-27",
        "review_date": "2026-09-21",
        "review_data": review_data,
        "agent_name": "weekly-review",
        "agent_version": "1.0",
    }


def _prescription(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": "2026-09-24",
        "session_type": "easy",
        "title": "イージー",
        "target_minutes": 40,
        "hr_high": 141,
        "rationale": "平常",
    }
    row.update(overrides)
    return row


@pytest.mark.integration
def test_insert_weekly_review_rejects_emoji_prose(initialized_db_path: Path) -> None:
    db_path = str(initialized_db_path)
    before = _count(db_path, "weekly_reviews")

    with pytest.raises(ValueError, match=r"save_weekly_review: .*\boverall\b"):
        insert_weekly_review(_review({"overall": "🟡注意"}), db_path=db_path)

    assert _count(db_path, "weekly_reviews") == before


@pytest.mark.integration
def test_insert_weekly_prescriptions_allows_rating_emoji(
    initialized_db_path: Path,
) -> None:
    db_path = str(initialized_db_path)

    result = insert_weekly_prescriptions(
        "2026-09-21", [_prescription(rating="✅")], db_path=db_path
    )
    assert result["count"] == 1

    with pytest.raises(ValueError, match=r"save_weekly_prescriptions: .*rationale"):
        insert_weekly_prescriptions(
            "2026-09-21", [_prescription(rationale="✅")], db_path=db_path
        )


@pytest.mark.integration
def test_insert_athlete_profile_rejects_emoji_focus_notes(
    initialized_db_path: Path,
) -> None:
    db_path = str(initialized_db_path)
    before = _count(db_path, "athlete_profile_versions")

    with pytest.raises(ValueError, match=r"save_athlete_profile: .*focus_notes"):
        insert_athlete_profile(
            {"user_id": "default", "focus_notes": "🟢絞る週"}, db_path=db_path
        )

    assert _count(db_path, "athlete_profile_versions") == before


@pytest.mark.integration
def test_insert_trend_analysis_rejects_emoji(initialized_db_path: Path) -> None:
    db_path = str(initialized_db_path)
    before = _count(db_path, "trend_analyses")

    with pytest.raises(ValueError, match=r"save_trend_narration: .*headline"):
        insert_trend_analysis(
            {
                "granularity": "week",
                "period_start": "2026-09-21",
                "period_end": "2026-09-27",
                "analysis_data": {"headline": "📈 伸びています"},
            },
            db_path=db_path,
        )

    assert _count(db_path, "trend_analyses") == before


@pytest.mark.integration
def test_insert_symptom_rejects_emoji_note(initialized_db_path: Path) -> None:
    with pytest.raises(ValueError, match="save_symptom"):
        insert_symptom(
            {
                "date": "2026-09-21",
                "body_region": "calf",
                "severity": 2,
                "phase": "after",
                "note": "😣 張り",
            },
            db_path=str(initialized_db_path),
        )


@pytest.mark.integration
def test_insert_training_blocks_rejects_emoji(initialized_db_path: Path) -> None:
    with pytest.raises(ValueError, match=r"save_training_blocks: .*\[0\]\.notes"):
        insert_training_blocks(
            [
                {
                    "phase": "build",
                    "title": "ビルド",
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-30",
                    "notes": "🔥 山場",
                }
            ],
            db_path=str(initialized_db_path),
        )


@pytest.mark.integration
def test_writer_refuses_section_analysis_with_emoji(
    initialized_db_path: Path,
) -> None:
    db_path = str(initialized_db_path)
    before = _count(db_path, "section_analyses")

    ok = GarminDBWriter(db_path=db_path).insert_section_analysis(
        activity_id=990001428,
        activity_date="2026-09-09",
        section_type="run_note",
        analysis_data={"story": "✅ 処方どおり"},
    )

    assert ok is False
    assert _count(db_path, "section_analyses") == before
