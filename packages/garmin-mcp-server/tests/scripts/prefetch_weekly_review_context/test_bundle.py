"""prefetch_weekly_review_context bundle shape with mocked readers: keys, training block / ladder, adherence, prescriptions, Garmin conflicts."""

from __future__ import annotations

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import (
    _block,
    _ladder,
    _mock_prefetch,
)


@pytest.mark.unit
def test_prefetch_bundle_safe_null_on_reader_error() -> None:
    """One failing reader nulls its key; the rest of the bundle survives."""
    with _mock_prefetch(load_trend_raises=True):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "error" not in result
    # The failing collector is null; siblings are populated.
    assert result["load_trend"] is None
    assert result["acwr"] == {"acwr": 1.0}
    # Network calendar reader raised -> null, but the key is still present.
    assert result["scheduled_workouts"] is None
    for key in (
        "week_start_date",
        "week_end_date",
        "prev_start",
        "prev_end",
        "week_in_progress",
        "week_start_day",
        "as_of",
        "activity_ids",
        "activities",
        "fitness_summary",
        "recovery",
        "strength",
        "hiking",
        "training_block",
        "prescriptions_prev_week",
        "prescriptions_current_week",
        "garmin_conflicts",
        "athlete_profile",
        "goals_with_weeks_to_race",
        "past_review",
    ):
        assert key in result


@pytest.mark.unit
def test_prefetch_bundle_has_hiking_key() -> None:
    """The bundle carries hiking.{prev_week, current_week} (issue #921)."""
    with _mock_prefetch() as reader:
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert set(result["hiking"]) == {"prev_week", "current_week"}
    assert result["hiking"] == {"prev_week": [], "current_week": []}
    # Both windows are read from the hiking reader (W-1 and W).
    assert reader.get_hiking_sessions.call_count == 2
    assert reader.get_hiking_sessions.call_args_list[0].args == (
        "2026-06-29",
        "2026-07-05",
    )
    assert reader.get_hiking_sessions.call_args_list[1].args == (
        "2026-07-06",
        "2026-07-12",
    )


@pytest.mark.unit
def test_prefetch_includes_training_block_and_ladder_step() -> None:
    """The bundle carries W's block, its ladder step and the block runway."""
    with _mock_prefetch(block=_block(), ladder_step=_ladder()) as reader:
        result = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    training_block = result["training_block"]
    assert training_block["block"]["title"] == "新潟ビルド"
    assert training_block["ladder_step"]["current"]["target_km"] == 22.0
    assert training_block["ladder_step"]["previous"]["target_km"] == 19.0
    # 2026-09-07 -> block end 2026-09-27 is two further weeks.
    assert training_block["weeks_to_block_end"] == 2
    assert training_block["weight_mode"] == "維持"
    assert training_block["quality_sessions_per_week"] == 1
    assert training_block["quality_types"] == ["threshold"]
    # The other readers still ran (additive key, not a replacement).
    assert reader.get_acwr.called


@pytest.mark.unit
def test_prefetch_training_block_null_when_none() -> None:
    """No block registered -> the key is present with null fields, no exception."""
    with _mock_prefetch():
        result = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    training_block = result["training_block"]
    assert training_block["block"] is None
    assert training_block["ladder_step"] == {
        "current": None,
        "previous": None,
        "next": None,
    }
    assert training_block["weeks_to_block_end"] is None
    assert training_block["quality_sessions_per_week"] is None
    assert training_block["quality_types"] == []


@pytest.mark.unit
def test_prefetch_prev_week_adherence() -> None:
    """W-1's prescriptions ship with their deterministic adherence counts."""
    rows = [
        {"date": "2026-09-01", "session_type": "easy", "status": "done"},
        {"date": "2026-09-03", "session_type": "threshold", "status": "done"},
        {"date": "2026-09-06", "session_type": "long", "status": "replaced"},
    ]
    with _mock_prefetch(prev_prescriptions=rows):
        result = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    prev = result["prescriptions_prev_week"]
    assert prev["rows"] == rows
    assert prev["adherence"]["done"] == 2
    assert prev["adherence"]["replaced"] == 1
    assert prev["adherence"]["prescribed"] == 3


@pytest.mark.unit
def test_bundle_has_prescriptions_current_week() -> None:
    """W's canonical batch ships with its batch_id / review_id (#1021)."""
    current = [
        {
            "date": "2026-09-09",
            "session_type": "easy",
            "title": "Z2ジョグ 計25分",
            "batch_id": 4,
            "review_id": 59,
            "rating": "🟡",
        },
        {
            "date": "2026-09-13",
            "session_type": "long",
            "title": "ロング 22km",
            "batch_id": 4,
            "review_id": 59,
            "rating": "✅",
        },
    ]
    with _mock_prefetch(
        prescriptions_by_week={"2026-09-07": current, "2026-08-31": []}
    ):
        result = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    bundle = result["prescriptions_current_week"]
    assert len(bundle["rows"]) == 2
    assert bundle["batch_id"] == 4
    assert bundle["review_id"] == 59
    assert bundle["rows"][0]["rating"] == "🟡"

    with _mock_prefetch(prescriptions_by_week={}):
        empty = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    assert empty["prescriptions_current_week"] == {
        "rows": [],
        "batch_id": None,
        "review_id": None,
    }


@pytest.mark.unit
def test_prefetch_garmin_conflicts_present() -> None:
    """Garmin items beyond the block's quality budget surface as conflicts."""
    with _mock_prefetch(
        block=_block(),
        ladder_step=_ladder(),
        scheduled=[
            {"date": "2026-09-08", "title": "Tempo"},
            {"date": "2026-09-10", "title": "Threshold"},
        ],
    ):
        result = prefetch_weekly_review_context("2026-09-07", today="2026-09-07")

    assert result["scheduled_workouts"]["count"] == 2
    assert len(result["garmin_conflicts"]) == 1
    assert result["garmin_conflicts"][0] == {
        "date": "2026-09-10",
        "garmin_title": "Threshold",
        "reason": "second_quality_session",
    }
