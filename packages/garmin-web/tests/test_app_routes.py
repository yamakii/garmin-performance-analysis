"""Regression tests for router wiring in create_app().

Guards that the retired ``/api/planned-workouts/today`` endpoint (Issue #786)
stays removed after the Today "今日の予定" card was dropped (#781).
"""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from garmin_web.app import create_app


@pytest.mark.unit
def test_today_plan_endpoint_removed() -> None:
    """GET /api/planned-workouts/today is no longer a registered route (404)."""
    client = TestClient(create_app())
    response = client.get("/api/planned-workouts/today")
    assert response.status_code == 404


@pytest.mark.unit
def test_app_router_list_excludes_planned() -> None:
    """No API route path references planned workouts."""
    app = create_app()
    api_paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert all("planned" not in path for path in api_paths)
