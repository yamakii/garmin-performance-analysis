"""Response-shape contract tests against frontend TypeScript interfaces.

A lightweight alternative to full OpenAPI -> TS codegen (Issue #350): each API
endpoint is exercised against the existing tmp-DB fixtures and asserted to carry
the **required keys with the right types** that the React frontend's
``frontend/src/types.ts`` interfaces depend on.

Drift detection model
---------------------
- Flat, fully-specified interfaces (``ActivitySummary``, ``WeeklyReview``) get a
  **superset check**: every required (non-optional) TS key must be present in the
  response. A backend rename/drop fails the test.
- The ``SELECT *`` path (``ActivityDetailResponse.activity``) gets a **subset
  existence check** only — pinning every DB column would be over-scoped, so we
  assert the frontend-referenced keys exist (per the issue's guidance).
- Nullable TS fields (``T | null``) are allowed to be ``None``; non-nullable
  fields must be present and non-None with the expected Python type.

All tests use tmp-DB fixtures from ``conftest.py`` — no production data.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

# Mirrors conftest.FULL_ACTIVITY_ID (fully-populated detail fixture row).
FULL_ACTIVITY_ID = 9000000101

# --- Required-key contracts derived from frontend/src/types.ts ---------------
# Each maps a TS key -> the Python type(s) a non-null value must have.
# ``None`` is always tolerated here; "must be non-null" is enforced separately
# via the *_NON_NULL key sets below.

# ActivitySummary (types.ts L1-9): every key is required; 5 of them nullable.
_ACTIVITY_SUMMARY_TYPES: dict[str, type | tuple[type, ...]] = {
    "activity_id": int,
    "activity_date": str,
    "activity_name": str,
    "total_distance_km": (int, float),
    "total_time_seconds": int,
    "avg_pace_seconds_per_km": (int, float),
    "avg_heart_rate": int,
}
# Non-nullable in ActivitySummary.
_ACTIVITY_SUMMARY_NON_NULL = {"activity_id", "activity_date"}

# ActivityDetailResponse top-level keys (types.ts L146-155): all required.
_DETAIL_TOP_LEVEL_KEYS = {
    "activity",
    "splits",
    "form_efficiency",
    "hr_zones",
    "performance_trends",
    "form_evaluations",
    "vo2_max",
    "lactate_threshold",
}

# SplitRow required (non-optional) keys (types.ts L112-122).
_SPLIT_ROW_NON_NULL = {"activity_id", "split_index"}
# HrZoneRow required (non-optional) keys (types.ts L124-131).
_HR_ZONE_NON_NULL = {"activity_id", "zone_number"}

# WeeklyReview required (non-optional) keys (types.ts L96-106).
_WEEKLY_REVIEW_TYPES: dict[str, type | tuple[type, ...]] = {
    "review_id": int,
    "user_id": str,
    "week_start_date": str,
    "week_end_date": str,
    "review_date": str,
    "review_data": dict,
    "created_at": str,
    "agent_name": str,
    "agent_version": str,
}
_WEEKLY_REVIEW_NON_NULL = {
    "review_id",
    "user_id",
    "week_start_date",
    "week_end_date",
}

# GoalResponse nested required keys (types.ts L13-44).
_GOAL_PROFILE_KEYS = {"current_focus", "focus_notes", "updated_at"}
_GOAL_RACE_KEYS = {
    "goal_id",
    "race_name",
    "race_date",
    "priority",
    "goal_type",
    "distance_km",
    "target_time_seconds",
    "status",
    "notes",
}
_RETROSPECTIVE_KEYS = {
    "retro_id",
    "season_label",
    "period_start",
    "period_end",
    "narrative",
    "key_learnings",
}


def _assert_keys_present(obj: dict, keys: set[str], where: str) -> None:
    """Every key in ``keys`` must be present in ``obj`` (superset check)."""
    missing = keys - set(obj.keys())
    assert not missing, f"{where}: missing required keys {sorted(missing)}"


def _assert_typed_keys(
    obj: dict,
    type_map: dict[str, type | tuple[type, ...]],
    non_null: set[str],
    where: str,
) -> None:
    """Assert each key exists; non-null keys are non-None and typed correctly.

    Nullable keys (not in ``non_null``) may be ``None`` but, when present and
    non-None, must still match the declared Python type. ``bool`` is rejected
    where an ``int`` is expected (bools are ints in Python but never valid here).
    """
    _assert_keys_present(obj, set(type_map), where)
    for key, expected in type_map.items():
        value = obj[key]
        if key in non_null:
            assert value is not None, f"{where}.{key} must be non-null"
        if value is None:
            continue
        assert isinstance(value, expected) and not isinstance(
            value, bool
        ), f"{where}.{key}={value!r} is not {expected}"


@pytest.mark.integration
def test_activities_response_contract(fixture_db_path: Any) -> None:
    """GET /api/activities -> each element matches ActivitySummary keys/types."""
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list) and len(payload) == 2
    for item in payload:
        _assert_typed_keys(
            item,
            _ACTIVITY_SUMMARY_TYPES,
            _ACTIVITY_SUMMARY_NON_NULL,
            "ActivitySummary",
        )


@pytest.mark.integration
def test_activity_detail_response_contract(detail_db_path: Any) -> None:
    """GET /api/activities/{id} -> ActivityDetailResponse required shape.

    The ``activity`` block comes from ``SELECT *`` so only the
    frontend-referenced ``ActivitySummary`` keys are asserted (subset existence),
    not every DB column.
    """
    client = TestClient(create_app(db_path=detail_db_path))
    response = client.get(f"/api/activities/{FULL_ACTIVITY_ID}")

    assert response.status_code == 200
    detail = response.json()

    # All ActivityDetailResponse top-level keys must be present.
    _assert_keys_present(detail, _DETAIL_TOP_LEVEL_KEYS, "ActivityDetailResponse")

    # activity: subset existence of ActivitySummary keys (SELECT * path).
    activity = detail["activity"]
    assert isinstance(activity, dict)
    _assert_typed_keys(
        activity,
        _ACTIVITY_SUMMARY_TYPES,
        _ACTIVITY_SUMMARY_NON_NULL,
        "ActivityDetailResponse.activity",
    )

    # splits / hr_zones are lists; each row carries its required keys.
    assert isinstance(detail["splits"], list) and detail["splits"]
    for split in detail["splits"]:
        _assert_keys_present(split, _SPLIT_ROW_NON_NULL, "SplitRow")
        assert split["activity_id"] == FULL_ACTIVITY_ID
        assert isinstance(split["split_index"], int)

    assert isinstance(detail["hr_zones"], list) and detail["hr_zones"]
    for zone in detail["hr_zones"]:
        _assert_keys_present(zone, _HR_ZONE_NON_NULL, "HrZoneRow")
        assert isinstance(zone["zone_number"], int)


@pytest.mark.integration
def test_trends_response_contract(trends_db_path: Any) -> None:
    """GET /api/trends/* -> required keys for each trend endpoint shape."""
    client = TestClient(create_app(db_path=trends_db_path))

    # volume: list of {bucket, distance_km, duration_seconds, run_count}
    volume = client.get("/api/trends/volume")
    assert volume.status_code == 200
    volume_rows = volume.json()
    assert isinstance(volume_rows, list) and volume_rows
    for row in volume_rows:
        _assert_keys_present(
            row,
            {"bucket", "distance_km", "duration_seconds", "run_count"},
            "VolumeTrendRow",
        )
        assert isinstance(row["bucket"], str)
        assert isinstance(row["run_count"], int)

    # physiology: {vo2max: [...], lactate_threshold: [...]}
    physiology = client.get("/api/trends/physiology")
    assert physiology.status_code == 200
    phys = physiology.json()
    _assert_keys_present(phys, {"vo2max", "lactate_threshold"}, "PhysiologyTrend")
    assert isinstance(phys["vo2max"], list)
    assert isinstance(phys["lactate_threshold"], list)
    for point in phys["vo2max"]:
        _assert_keys_present(point, {"date", "value"}, "Vo2MaxPoint")

    # form: list of {date, overall_score, gct_delta, vo_delta, vr_delta}
    form = client.get("/api/trends/form")
    assert form.status_code == 200
    form_rows = form.json()
    assert isinstance(form_rows, list) and form_rows
    for row in form_rows:
        _assert_keys_present(
            row,
            {"date", "overall_score", "gct_delta", "vo_delta", "vr_delta"},
            "FormTrendRow",
        )
        assert isinstance(row["date"], str)

    # efficiency: list with date + zone distribution
    efficiency = client.get("/api/trends/efficiency")
    assert efficiency.status_code == 200
    eff_rows = efficiency.json()
    assert isinstance(eff_rows, list) and eff_rows
    for row in eff_rows:
        _assert_keys_present(
            row,
            {
                "date",
                "aerobic_efficiency",
                "primary_zone",
                "zone1_percentage",
                "zone2_percentage",
                "zone3_percentage",
                "zone4_percentage",
                "zone5_percentage",
            },
            "EfficiencyTrendRow",
        )


@pytest.mark.integration
def test_goal_response_contract(goal_db_path: Any) -> None:
    """GET /api/goal -> GoalResponse nested required keys (profile/goals/retro)."""
    client = TestClient(create_app(db_path=goal_db_path))
    response = client.get("/api/goal")

    assert response.status_code == 200
    payload = response.json()
    _assert_keys_present(
        payload, {"profile", "goals", "retrospectives"}, "GoalResponse"
    )

    _assert_keys_present(payload["profile"], _GOAL_PROFILE_KEYS, "GoalProfile")

    assert isinstance(payload["goals"], list) and payload["goals"]
    for goal in payload["goals"]:
        _assert_keys_present(goal, _GOAL_RACE_KEYS, "GoalRace")
        assert isinstance(goal["goal_id"], int)

    assert isinstance(payload["retrospectives"], list) and payload["retrospectives"]
    for retro in payload["retrospectives"]:
        _assert_keys_present(retro, _RETROSPECTIVE_KEYS, "SeasonRetrospective")
        assert isinstance(retro["retro_id"], int)


@pytest.mark.integration
def test_weekly_reviews_response_contract(weekly_reviews_db_path: Any) -> None:
    """GET /api/weekly-reviews -> each element matches WeeklyReview keys/types."""
    client = TestClient(create_app(db_path=weekly_reviews_db_path))
    response = client.get("/api/weekly-reviews")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list) and payload
    for review in payload:
        _assert_typed_keys(
            review,
            _WEEKLY_REVIEW_TYPES,
            _WEEKLY_REVIEW_NON_NULL,
            "WeeklyReview",
        )
