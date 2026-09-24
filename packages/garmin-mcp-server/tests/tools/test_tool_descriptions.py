"""Every MCP tool carries a contract-level description (Issue #1375).

A tool's description and its parameter descriptions are the only contract the
model sees before calling it, so a one-line summary or an undocumented argument
leaves it guessing what the tool returns or what an ID means.
"""

import pytest

from garmin_mcp.tool_schemas import get_tool_definitions

_MIN_DESCRIPTION_CHARS = 80


@pytest.mark.unit
def test_every_tool_param_has_description() -> None:
    missing = [
        f"{tool.name}.{name}"
        for tool in get_tool_definitions()
        for name, prop in (tool.input_schema or {}).get("properties", {}).items()
        if not prop.get("description")
    ]
    assert missing == []


@pytest.mark.unit
def test_every_tool_description_is_substantive() -> None:
    short = [
        f"{tool.name} ({len(tool.description or '')} chars)"
        for tool in get_tool_definitions()
        if len(tool.description or "") < _MIN_DESCRIPTION_CHARS
    ]
    assert short == []
