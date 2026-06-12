"""Tests for SPA static serving and fallback in create_app()."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app

_INDEX_HTML = "<!doctype html><html><body>garmin-web spa</body></html>"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """Fake frontend build output with an index.html."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(_INDEX_HTML)
    return dist


@pytest.mark.unit
def test_spa_fallback_serves_index(static_dir):
    client = TestClient(create_app(static_dir=static_dir))
    response = client.get("/activities/123")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "garmin-web spa" in response.text


@pytest.mark.unit
def test_api_routes_not_shadowed(fixture_db_path, static_dir):
    client = TestClient(create_app(db_path=fixture_db_path, static_dir=static_dir))
    response = client.get("/api/activities")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 2


@pytest.mark.unit
def test_missing_dist_api_still_works(fixture_db_path, tmp_path):
    app = create_app(db_path=fixture_db_path, static_dir=tmp_path / "does-not-exist")
    client = TestClient(app)
    response = client.get("/api/activities")

    assert response.status_code == 200
    assert len(response.json()) == 2
