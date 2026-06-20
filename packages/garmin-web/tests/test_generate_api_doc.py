"""Tests for the generated web API endpoint table (Issue #436)."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI

from garmin_web.app import create_app
from garmin_web.scripts.generate_api_doc import (
    DOC_PATH,
    apply_generated_block,
    collect_endpoints,
    main,
    render_api_table,
    render_doc,
)


@pytest.mark.unit
def test_collect_endpoints_includes_goal_route() -> None:
    """The real app's routes include `/api/goal` with a description."""
    endpoints = collect_endpoints(create_app())
    paths = [path for path, _ in endpoints]
    assert "/api/goal" in paths
    description = dict(endpoints)["/api/goal"]
    assert description.strip()  # non-empty docstring-derived description


@pytest.mark.unit
def test_collect_endpoints_only_get() -> None:
    """Non-GET and non-/api routes are excluded; GET /api routes are kept."""
    app = FastAPI()
    router = APIRouter(prefix="/api")

    @router.get("/kept")
    def kept() -> dict:
        """Kept GET endpoint."""
        return {}

    @router.post("/written")
    def written() -> dict:
        """Excluded because it is a POST."""
        return {}

    @router.get("/hidden", include_in_schema=False)
    def hidden() -> dict:
        """Excluded because it is not in the schema."""
        return {}

    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        """Excluded because it is not under /api."""
        return {}

    paths = [path for path, _ in collect_endpoints(app)]
    assert paths == ["/api/kept"]


@pytest.mark.unit
def test_render_api_table_wraps_in_markers() -> None:
    """The rendered block starts/ends with the sentinel markers and lists rows."""
    block = render_api_table([("/api/foo", "Foo endpoint.")])
    assert block.startswith("<!-- BEGIN GENERATED: web-api-table -->")
    assert block.endswith("<!-- END GENERATED: web-api-table -->")
    assert "| `/api/foo` | Foo endpoint. |" in block


@pytest.mark.unit
def test_apply_raises_on_missing_marker() -> None:
    """A doc with no markers raises ValueError."""
    with pytest.raises(ValueError, match="missing BEGIN marker"):
        apply_generated_block("# Title\n\nNo markers.\n", "anything")


@pytest.mark.integration
def test_api_doc_in_sync() -> None:
    """Committed garmin-web.md API table == generated output."""
    committed = DOC_PATH.read_text(encoding="utf-8")
    rendered = render_doc(committed)
    assert committed == rendered, (
        "docs/garmin-web.md API table is out of sync with the FastAPI routes. "
        "Regenerate: python -m garmin_web.scripts.generate_api_doc"
    )


@pytest.mark.integration
def test_check_mode_passes_when_in_sync() -> None:
    """`main(['--check'])` returns 0 when the committed doc matches the routes."""
    assert main(["--check"]) == 0
