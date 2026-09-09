"""Bundle slimming: athlete profile, recovery series, past review, single goals copy."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from garmin_mcp.scripts.prefetch_weekly_review_context import (
    _RECOVERY_SERIES_KEEP_DAYS,
    _slim_athlete_profile,
    _slim_past_review,
    _slim_recovery_trend,
    _weeks_to_race,
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import _mock_prefetch


@pytest.mark.unit
def test_slim_athlete_profile_drops_goals() -> None:
    """The profile's duplicate goals copy is dropped, everything else stays."""
    profile = {"goals": [{"race_name": "新潟"}], "focus_notes": "x"}

    slim = _slim_athlete_profile(profile)

    assert slim is not None
    assert "goals" not in slim
    assert slim["focus_notes"] == "x"
    # The reader's dict is untouched (the caller still derives goals from it).
    assert "goals" in profile
    assert _slim_athlete_profile(None) is None


@pytest.mark.unit
def test_slim_recovery_series_keeps_last_14_days() -> None:
    """Only the recent tail of the daily series survives; aggregates are kept."""
    start = date(2026, 6, 22)
    series = [
        {
            "date": str(start + timedelta(days=i)),
            "resting_hr": 48 + (i % 3),
            "hrv_overnight_ms": 60 + i,
        }
        for i in range(57)
    ]
    trend = {
        "weeks": 8,
        "rhr": {"median_7d": 48, "median_30d": 50, "rhr_trend": "stable"},
        "hrv": {"latest_ms": 62, "hrv_below_baseline_days": 1},
        "series": series,
    }

    slim = _slim_recovery_trend(trend)

    assert slim is not None
    assert len(slim["series"]) == _RECOVERY_SERIES_KEEP_DAYS == 14
    assert slim["series"] == series[-14:]
    # The latest day is retained (the tail, not the head, is what is read).
    assert slim["series"][-1]["date"] == str(start + timedelta(days=56))
    # 8-week aggregates are carried through unchanged (never recomputed).
    assert slim["rhr"] == trend["rhr"]
    assert slim["hrv"] == trend["hrv"]
    assert slim["weeks"] == 8
    # The reader's dict is untouched.
    assert len(series) == 57

    # A series-less trend (and None) passes through unchanged.
    no_series = {"weeks": 8, "rhr": {"median_7d": None}}
    assert _slim_recovery_trend(no_series) == no_series
    assert _slim_recovery_trend(None) is None


@pytest.mark.unit
def test_slim_past_review_drops_replay_keys() -> None:
    """Stale actuals/plan replays go; the continuity keys stay."""
    review = {
        "week_start_date": "2026-08-10",
        "review_data": {
            "this_week": {"volume_km": 30.0},
            "garmin_next_week": [{"date": "2026-08-11", "title": "Base"}],
            "verdict": [{"date": "2026-08-11", "rating": "✅"}],
            "recommendations": ["Z2 141-152bpm で 60 分"],
        },
    }

    slim = _slim_past_review(review)

    assert slim is not None
    assert "this_week" not in slim["review_data"]
    assert "garmin_next_week" not in slim["review_data"]
    assert slim["review_data"]["verdict"] == [{"date": "2026-08-11", "rating": "✅"}]
    assert slim["review_data"]["recommendations"] == ["Z2 141-152bpm で 60 分"]
    assert slim["week_start_date"] == "2026-08-10"
    # The reader's dict is untouched.
    assert "this_week" in review["review_data"]

    # A non-dict review_data (and None) passes through unchanged.
    raw = {"review_data": '{"this_week": {}}'}
    assert _slim_past_review(raw) == raw
    assert _slim_past_review(None) is None


@pytest.mark.unit
def test_prefetch_bundle_goals_single_copy() -> None:
    """Goals ship once, in goals_with_weeks_to_race (not in athlete_profile)."""
    profile = {
        "current_focus": "base",
        "goals": [{"race_name": "新潟", "race_date": "2026-10-11"}],
    }
    with _mock_prefetch(profile=profile):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert "goals" not in result["athlete_profile"]
    assert result["athlete_profile"]["current_focus"] == "base"

    goals = result["goals_with_weeks_to_race"]
    assert len(goals) == 1
    assert goals[0]["race_name"] == "新潟"
    assert goals[0]["weeks_to_race"] == _weeks_to_race("2026-10-11", date(2026, 7, 6))


@pytest.mark.unit
def test_prefetch_bundle_trims_recovery_series_and_past_review() -> None:
    """The recovery-series / past-review trims are wired into the bundle."""
    series = [
        {"date": str(date(2026, 5, 15) + timedelta(days=i)), "resting_hr": 48}
        for i in range(57)
    ]
    past_review = {
        "week_start_date": "2026-06-29",
        "review_data": {
            "this_week": {"volume_km": 30.0},
            "garmin_next_week": [{"date": "2026-06-30", "title": "Base"}],
            "overall": "順調に積めています",
        },
    }
    with _mock_prefetch(past_review=past_review) as reader:
        reader.get_recovery_trend.return_value = {"weeks": 8, "series": series}
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["recovery"]["trend"]["series"] == series[-14:]
    assert set(result["past_review"]["review_data"]) == {"overall"}
