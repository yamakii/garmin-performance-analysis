"""Unit tests for garmin_web.queries.activities.list_activities."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.activities import list_activities


@pytest.mark.unit
def test_list_activities_returns_all_sorted(fixture_db_path):
    with get_connection(fixture_db_path) as conn:
        activities = list_activities(conn)

    assert len(activities) == 2
    assert activities[0]["activity_date"] == "2025-10-09"
    assert activities[1]["activity_date"] == "2025-10-07"
    assert all(isinstance(a["activity_date"], str) for a in activities)


@pytest.mark.unit
def test_list_activities_date_filter(fixture_db_path):
    with get_connection(fixture_db_path) as conn:
        activities = list_activities(conn, from_date="2025-10-08")

    assert len(activities) == 1
    assert activities[0]["activity_date"] == "2025-10-09"


@pytest.mark.unit
def test_list_activities_empty_db(empty_db_path):
    with get_connection(empty_db_path) as conn:
        activities = list_activities(conn)

    assert activities == []
