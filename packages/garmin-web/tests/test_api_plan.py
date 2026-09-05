"""Tests for the monthly plan query and API (Issue #983).

The fixture month is September 2026: 9/1 is a Tuesday, so with a Monday week
start the grid spans 2026-08-31 .. 2026-10-04 (5 rows) and the Sunday long run
is the last column of every row.

Marker convention follows the rest of this package: anything that touches a
DuckDB connection is `integration`, pure helpers are `unit`.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app
from garmin_web.queries.plan import get_month_plan, list_training_blocks


def _week(plan: dict, week_start: str) -> dict:
    """The grid row starting on ``week_start``."""
    return next(w for w in plan["weeks"] if w["week_start"] == week_start)


def _day(plan: dict, date: str) -> dict:
    """The day cell for ``date`` anywhere in the grid."""
    return next(d for week in plan["weeks"] for d in week["days"] if d["date"] == date)


# --- get_month_plan -------------------------------------------------------


@pytest.mark.integration
def test_get_month_plan_grid_range_covers_partial_weeks(plan_conn) -> None:
    """The grid starts on the week containing day 1 and ends on the last week."""
    plan = get_month_plan(plan_conn, "2026-09")

    assert plan["month"] == "2026-09"
    assert plan["week_start_day"] == 0
    assert len(plan["weeks"]) == 5
    assert plan["weeks"][0]["week_start"] == "2026-08-31"
    assert plan["weeks"][-1]["week_end"] == "2026-10-04"
    assert all(len(week["days"]) == 7 for week in plan["weeks"])

    # The spill days of the edge weeks are marked, so the grid can mute them.
    assert _day(plan, "2026-08-31")["in_month"] is False
    assert _day(plan, "2026-09-01")["in_month"] is True
    assert _day(plan, "2026-10-04")["in_month"] is False
    # ...and so are the edge rows themselves (a partial week is not in-month).
    assert _week(plan, "2026-08-31")["in_month"] is False
    assert _week(plan, "2026-09-07")["in_month"] is True


@pytest.mark.integration
def test_get_month_plan_merges_prescriptions_and_activities(plan_conn) -> None:
    """A day cell carries both what was prescribed and what was actually run."""
    plan = get_month_plan(plan_conn, "2026-09")

    long_day = _day(plan, "2026-09-13")
    assert [p["session_type"] for p in long_day["prescriptions"]] == ["long"]
    prescription = long_day["prescriptions"][0]
    assert prescription["target_km"] == 22.0
    assert prescription["hr_high"] == 150
    assert prescription["status"] == "done"

    assert [a["activity_id"] for a in long_day["activities"]] == [9000000103]
    assert long_day["activities"][0]["total_distance_km"] == 21.4
    assert long_day["activities"][0]["avg_pace_seconds_per_km"] == 378.5

    # A rest day has neither, and an out-of-month day still shows its run.
    assert _day(plan, "2026-09-09")["prescriptions"] == []
    assert _day(plan, "2026-08-31")["activities"][0]["activity_id"] == 9000000101


@pytest.mark.integration
def test_get_month_plan_week_adherence(plan_conn) -> None:
    """Week 9/14 (done / done / skipped / pending) counts as 4 prescribed."""
    plan = get_month_plan(plan_conn, "2026-09")

    assert _week(plan, "2026-09-14")["adherence"] == {
        "prescribed": 4,
        "done": 2,
        "replaced": 0,
        "skipped": 1,
        "pending": 1,
    }
    # The month total covers in-month days only (8/31 and 10/1-4 are excluded).
    assert plan["adherence"] == {
        "prescribed": 6,
        "done": 4,
        "replaced": 0,
        "skipped": 1,
        "pending": 1,
    }


@pytest.mark.integration
def test_get_month_plan_ignores_superseded_batch(plan_conn) -> None:
    """Only the latest batch of a week is canonical (append-only writes)."""
    plan = get_month_plan(plan_conn, "2026-09")

    titles = [p["title"] for p in _day(plan, "2026-09-20")["prescriptions"]]
    assert titles == ["ロング 25km"]


@pytest.mark.integration
def test_get_month_plan_blocks_overlap_only(plan_conn) -> None:
    """Only blocks overlapping the grid range are returned, as band data."""
    plan = get_month_plan(plan_conn, "2026-09")

    assert [block["block_id"] for block in plan["blocks"]] == [2]
    band = plan["blocks"][0]
    assert band == {
        "block_id": 2,
        "phase": "build",
        "title": "新潟マラソン ビルド",
        "start_date": "2026-08-24",
        "end_date": "2026-10-11",
        "weight_mode": "微減",
        "quality_sessions_per_week": 2,
    }


@pytest.mark.integration
def test_get_month_plan_ladder_step_on_week(plan_conn) -> None:
    """Each week carries the long-run ladder step its block declares."""
    plan = get_month_plan(plan_conn, "2026-09")

    step = _week(plan, "2026-09-07")["ladder_step"]
    assert step is not None
    assert step["target_km"] == 22.0
    assert step["hr_ceiling"] == 150
    assert _week(plan, "2026-08-31")["ladder_step"]["target_km"] == 19.0
    # The block's ladder stops at 9/21, so the last row has no step.
    assert _week(plan, "2026-09-28")["ladder_step"] is None


@pytest.mark.integration
def test_get_month_plan_review_exists_per_week(plan_conn) -> None:
    """A week links to a saved review only when one exists for it."""
    plan = get_month_plan(plan_conn, "2026-09")

    assert _week(plan, "2026-09-07")["review_exists"] is True
    assert _week(plan, "2026-09-14")["review_exists"] is False


@pytest.mark.integration
def test_get_month_plan_empty_month_keeps_grid(plan_empty_conn) -> None:
    """An unplanned month still renders a full grid with zeroed adherence."""
    plan = get_month_plan(plan_empty_conn, "2026-09")

    assert len(plan["weeks"]) == 5
    assert plan["blocks"] == []
    assert plan["adherence"]["prescribed"] == 0
    assert all(week["ladder_step"] is None for week in plan["weeks"])


@pytest.mark.integration
def test_get_month_plan_without_ledger_tables(plan_legacy_conn) -> None:
    """A DB predating the ledger migrations renders an empty month, not a 500."""
    plan = get_month_plan(plan_legacy_conn, "2026-09")

    assert len(plan["weeks"]) == 5
    assert plan["blocks"] == []
    assert list_training_blocks(plan_legacy_conn) == []


@pytest.mark.unit
def test_get_month_plan_rejects_bad_month_format() -> None:
    """A non `YYYY-MM` month is rejected before any query runs."""
    with pytest.raises(ValueError, match="YYYY-MM"):
        get_month_plan(None, "2026-9")  # type: ignore[arg-type]


@pytest.mark.integration
def test_list_training_blocks_decodes_ladder(plan_conn) -> None:
    """The ledger is returned in sequence order with its JSON columns decoded."""
    blocks = list_training_blocks(plan_conn)

    assert [block["block_id"] for block in blocks] == [1, 2]
    assert blocks[1]["long_run_ladder"][1]["target_km"] == 22.0
    assert blocks[0]["long_run_ladder"] == []
    assert blocks[1]["start_date"] == "2026-08-24"


# --- API ------------------------------------------------------------------


@pytest.mark.integration
def test_api_plan_month_default_and_422(plan_db_path) -> None:
    """No `month` param means the current month; a malformed one is a 422."""
    client = TestClient(create_app(db_path=plan_db_path))

    response = client.get("/api/plan/month")
    assert response.status_code == 200
    payload = response.json()
    assert payload["month"] == _dt.date.today().strftime("%Y-%m")
    assert 4 <= len(payload["weeks"]) <= 6

    assert client.get("/api/plan/month?month=2026-9").status_code == 422
    assert client.get("/api/plan/month?month=2026-13").status_code == 422


@pytest.mark.integration
def test_api_plan_month_returns_requested_month(plan_db_path) -> None:
    """`?month=2026-09` returns that month's grid with its bands."""
    client = TestClient(create_app(db_path=plan_db_path))
    response = client.get("/api/plan/month?month=2026-09")

    assert response.status_code == 200
    payload = response.json()
    assert payload["weeks"][0]["week_start"] == "2026-08-31"
    assert len(payload["weeks"]) == 5
    assert payload["blocks"][0]["phase"] == "build"


@pytest.mark.integration
def test_api_plan_blocks(plan_db_path) -> None:
    """`/api/plan/blocks` returns the whole ledger in display order."""
    client = TestClient(create_app(db_path=plan_db_path))
    response = client.get("/api/plan/blocks")

    assert response.status_code == 200
    payload = response.json()
    assert [block["title"] for block in payload] == [
        "夏の有酸素ベース",
        "新潟マラソン ビルド",
    ]
