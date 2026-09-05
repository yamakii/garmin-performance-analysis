"""Tests for SPA static serving and fallback in create_app()."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from garmin_web.app import _resolve_static_file, create_app

_INDEX_HTML = "<!doctype html><html><body>garmin-web spa</body></html>"
_APP_JS = 'console.log("app")'


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """Fake frontend build output with an index.html and one asset."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(_INDEX_HTML)
    (dist / "assets" / "app.js").write_text(_APP_JS)
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
def test_resolve_static_file_returns_existing_asset(static_dir):
    root = static_dir.resolve()

    assert _resolve_static_file(root, "assets/app.js") == root / "assets" / "app.js"


@pytest.mark.unit
def test_resolve_static_file_returns_none_for_traversal(static_dir, tmp_path):
    """A ``..`` escape resolves outside the root and is refused (#996).

    The secret file really exists, so a ``None`` here proves containment is
    decided before the stat rather than by the file simply being absent.
    """
    (tmp_path / "secret.txt").write_text("top secret")

    assert _resolve_static_file(static_dir.resolve(), "../secret.txt") is None


@pytest.mark.unit
def test_resolve_static_file_returns_none_for_absolute_path(static_dir, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")

    assert _resolve_static_file(static_dir.resolve(), str(secret)) is None


@pytest.mark.unit
def test_spa_fallback_serves_existing_asset(static_dir):
    client = TestClient(create_app(static_dir=static_dir))
    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == _APP_JS


@pytest.mark.unit
def test_spa_fallback_traversal_serves_index(static_dir, tmp_path):
    """A traversing request falls back to the SPA, never to an outside file."""
    (tmp_path / "secret.txt").write_text("top secret")

    client = TestClient(create_app(static_dir=static_dir))
    response = client.get("/..%2Fsecret.txt")

    assert response.status_code == 200
    assert "top secret" not in response.text
    assert "garmin-web spa" in response.text


@pytest.mark.unit
def test_missing_dist_api_still_works(fixture_db_path, tmp_path):
    app = create_app(db_path=fixture_db_path, static_dir=tmp_path / "does-not-exist")
    client = TestClient(app)
    response = client.get("/api/activities")

    assert response.status_code == 200
    assert len(response.json()) == 2
