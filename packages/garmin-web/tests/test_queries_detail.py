"""Unit tests for garmin_web.queries.detail.get_activity_detail."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.detail import get_activity_detail

FULL_ACTIVITY_ID = 9000000101
PARTIAL_ACTIVITY_ID = 9000000102


@pytest.mark.unit
def test_detail_aggregates_tables(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, FULL_ACTIVITY_ID)

    assert detail is not None
    for key in (
        "activity",
        "splits",
        "form_efficiency",
        "hr_zones",
        "performance_trends",
        "form_evaluations",
    ):
        assert key in detail

    assert detail["activity"]["activity_id"] == FULL_ACTIVITY_ID
    assert detail["activity"]["activity_date"] == "2025-10-09"
    assert isinstance(detail["activity"]["activity_date"], str)

    # splits: 5 rows sorted by split_index ascending
    assert len(detail["splits"]) == 5
    assert [s["split_index"] for s in detail["splits"]] == [1, 2, 3, 4, 5]

    assert detail["form_efficiency"]["gct_average"] == 248.0
    assert len(detail["hr_zones"]) == 5
    assert [z["zone_number"] for z in detail["hr_zones"]] == [1, 2, 3, 4, 5]
    assert detail["performance_trends"]["pace_consistency"] == 4.2
    assert detail["form_evaluations"]["overall_score"] == pytest.approx(4.1)


@pytest.mark.unit
def test_detail_missing_activity_returns_none(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, 999999)

    assert detail is None


@pytest.mark.unit
def test_detail_partial_data(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, PARTIAL_ACTIVITY_ID)

    assert detail is not None
    assert detail["form_efficiency"] is None
    assert detail["performance_trends"] is None
    assert detail["form_evaluations"] is None
    assert detail["hr_zones"] == []
    # Other data is still returned
    assert detail["activity"]["activity_name"] == "Partial Run"
    assert len(detail["splits"]) == 2
