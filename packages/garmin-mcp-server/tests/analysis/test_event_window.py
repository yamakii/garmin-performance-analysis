"""Unit tests for the post-event protection window (#1219).

Every case feeds the two pure functions plain dicts -- no DB, no I/O. The
December 2025 half marathon (21.2 km at 141 bpm, followed 15 days later by a
28.6 km long run) is the worked example the module was written for.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.event_window import (
    compute_post_event_window,
    resolve_big_events,
)


def _event(date: str, source: str = "goal", label: str = "レース") -> dict[str, Any]:
    """Build a resolved-event dict."""
    return {"date": date, "source": source, "label": label, "activity_id": None}


def _run(activity_id: int, date: str, distance_km: float) -> dict[str, Any]:
    """Build an activity dict as ``compute_post_event_window`` expects it."""
    return {
        "activity_id": activity_id,
        "activity_date": date,
        "distance_km": distance_km,
    }


# ---------------------------------------------------------------------------
# resolve_big_events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_goal_and_ladder_union_dedup() -> None:
    """A goal and the ladder race week for it collapse into one goal event."""
    events = resolve_big_events(
        goals=[
            {
                "race_date": "2026-10-11",
                "race_name": "新潟シティマラソン",
                "status": "active",
            }
        ],
        ladder_steps=[{"week_start": "2026-10-05", "target_km": 42.2, "kind": "race"}],
        hard_long_runs=[],
    )

    assert len(events) == 1
    assert events[0]["date"] == "2026-10-11"
    assert events[0]["source"] == "goal"
    assert events[0]["label"] == "新潟シティマラソン"


@pytest.mark.unit
def test_hr_proxy_only_when_no_calendar_event() -> None:
    """The proxy needs >=18 km *and* an avg HR at the Garmin zone-3 floor."""
    events = resolve_big_events(
        goals=[],
        ladder_steps=[],
        hard_long_runs=[
            {
                "activity_id": 111,
                "activity_date": "2026-03-01",
                "distance_km": 19.0,
                "avg_heart_rate": 147,
                "zone3_lower": 151,
            },
            {
                "activity_id": 222,
                "activity_date": "2026-04-05",
                "distance_km": 25.0,
                "avg_heart_rate": 155,
                "zone3_lower": 151,
            },
        ],
    )

    assert [e["date"] for e in events] == ["2026-04-05"]
    assert events[0]["source"] == "hr_proxy"
    assert events[0]["activity_id"] == 222


@pytest.mark.unit
def test_half_at_141bpm_is_found_via_goal_not_hr() -> None:
    """The 2025-12-14 half is an event through the calendar despite 141 bpm."""
    events = resolve_big_events(
        goals=[
            {
                "race_date": "2025-12-14",
                "race_name": "ハーフマラソン",
                "status": "completed",
            }
        ],
        ladder_steps=[],
        hard_long_runs=[
            {
                "activity_id": 333,
                "activity_date": "2025-12-14",
                "distance_km": 21.2,
                "avg_heart_rate": 141,
                "zone3_lower": 151,
            }
        ],
    )

    assert len(events) == 1
    assert events[0]["date"] == "2025-12-14"
    assert events[0]["source"] == "goal"


# ---------------------------------------------------------------------------
# compute_post_event_window
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_2025_12_29_is_red() -> None:
    """The injury pattern: +34.9 % over the ceiling, 15 days after the half."""
    window = compute_post_event_window(
        events=[_event("2025-12-14", label="ハーフマラソン")],
        runs_since=[_run(444, "2025-12-29", 28.6)],
        pre_event_longest_km=21.2,
        date="2025-12-29",
    )

    assert window["days_since_event"] == 15
    assert window["in_window"] is True
    assert window["ceiling_km"] == 21.2
    assert window["longest_since_km"] == 28.6
    assert window["longest_since_activity_id"] == 444
    assert window["overshoot_pct"] == pytest.approx(34.9, abs=0.05)
    assert window["verdict"] == "red"
    assert "21.2km" in window["reason_ja"]


@pytest.mark.unit
def test_within_ceiling_is_green() -> None:
    """An 18 km run on day 10 stays under the 21.2 km ceiling -> green."""
    window = compute_post_event_window(
        events=[_event("2025-12-14")],
        runs_since=[_run(445, "2025-12-24", 18.0)],
        pre_event_longest_km=21.2,
        date="2025-12-24",
    )

    assert window["days_since_event"] == 10
    assert window["in_window"] is True
    assert window["verdict"] == "green"
    assert window["longest_since_km"] == 18.0


@pytest.mark.unit
def test_small_overshoot_is_yellow() -> None:
    """+7.5 % over the ceiling is above it but under the 10 % red line."""
    window = compute_post_event_window(
        events=[_event("2026-02-01")],
        runs_since=[_run(446, "2026-02-10", 21.5)],
        pre_event_longest_km=20.0,
        date="2026-02-10",
    )

    assert window["verdict"] == "yellow"
    assert window["overshoot_pct"] == pytest.approx(7.5, abs=0.05)


@pytest.mark.unit
def test_day_22_is_outside_window() -> None:
    """Day 22 is past the 21-day window, so the ceiling no longer applies."""
    window = compute_post_event_window(
        events=[_event("2026-02-01")],
        runs_since=[_run(447, "2026-02-22", 30.0)],
        pre_event_longest_km=20.0,
        date="2026-02-23",
    )

    assert window["days_since_event"] == 22
    assert window["in_window"] is False
    assert window["verdict"] == "green"


@pytest.mark.unit
def test_no_events() -> None:
    """No registered stimulus at all -> no_event, nothing to protect against."""
    window = compute_post_event_window(
        events=[],
        runs_since=[_run(448, "2026-02-10", 30.0)],
        pre_event_longest_km=20.0,
        date="2026-02-10",
    )

    assert window["verdict"] == "no_event"
    assert window["last_event"] is None
    assert window["days_since_event"] is None
    assert window["in_window"] is False


@pytest.mark.unit
def test_missing_ceiling_in_window() -> None:
    """Inside the window with no computable ceiling -> insufficient_data."""
    window = compute_post_event_window(
        events=[_event("2026-02-01")],
        runs_since=[_run(449, "2026-02-10", 22.0)],
        pre_event_longest_km=None,
        date="2026-02-10",
    )

    assert window["verdict"] == "insufficient_data"
    assert window["in_window"] is True
    assert window["ceiling_km"] is None
