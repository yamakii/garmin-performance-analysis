"""Tests for the MCP tool-reference generator (Issue #423)."""

from __future__ import annotations

import pytest

from garmin_mcp.scripts.generate_tool_reference import (
    DOC_PATH,
    main,
    render_reference,
)
from garmin_mcp.tool_schemas import _SERVER_TOOLS
from garmin_mcp.tools import ALL_DEFS


@pytest.mark.unit
def test_reference_is_in_sync() -> None:
    """Committed docs/mcp-tools-reference.md must equal the generated output.

    Fails when a tool is added/changed without regenerating the doc.
    """
    assert DOC_PATH.exists(), f"{DOC_PATH} missing; run the generator"
    committed = DOC_PATH.read_text(encoding="utf-8")
    assert committed == render_reference(), (
        "docs/mcp-tools-reference.md is out of sync with the ToolDef registry. "
        "Regenerate: python -m garmin_mcp.scripts.generate_tool_reference"
    )


@pytest.mark.unit
def test_all_tools_present() -> None:
    """Every registry + server tool name appears, and the count is 46."""
    content = render_reference()
    names = [d.name for d in ALL_DEFS] + [t["name"] for t in _SERVER_TOOLS]
    assert len(names) == 46
    for name in names:
        assert f"### `{name}`" in content, f"{name} missing from reference"


@pytest.mark.unit
def test_render_includes_params() -> None:
    """A known parameter is rendered in the params table."""
    content = render_reference()
    # splits tools share a statistics_only flag.
    assert "`statistics_only`" in content
    assert "**required**" in content
    assert "_No parameters._" in content  # get_server_info has none


@pytest.mark.unit
def test_check_mode_passes_when_in_sync() -> None:
    """`--check` returns 0 when the committed doc matches the registry."""
    assert main(["--check"]) == 0
