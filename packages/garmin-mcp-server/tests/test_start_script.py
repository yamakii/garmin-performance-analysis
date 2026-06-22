"""Unit tests for the MCP launcher shell script (Issue #481).

The launcher was simplified to a single ``exec`` of the bundled server package.
These tests guard that the override-dir branch (TTL check, override file,
fallback) is gone — code under development is validated in subprocess instead of
being swapped into the live launcher.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# repo-root scripts/start-mcp-server.sh, four parents up from this test file:
#   tests/test_start_script.py -> garmin-mcp-server -> packages -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_START_SCRIPT = _REPO_ROOT / "scripts" / "start-mcp-server.sh"


@pytest.mark.unit
def test_start_script_has_no_override_branch() -> None:
    """The launcher no longer references the override-dir mechanism."""
    text = _START_SCRIPT.read_text(encoding="utf-8")
    assert "OVERRIDE_FILE" not in text
    assert "garmin-mcp-server-dir" not in text
    assert "OVERRIDE_DIR" not in text


@pytest.mark.unit
def test_start_script_is_single_exec() -> None:
    """The launcher is a single ``exec uv run`` of the bundled package."""
    text = _START_SCRIPT.read_text(encoding="utf-8")
    exec_lines = [
        line.strip() for line in text.splitlines() if line.strip().startswith("exec ")
    ]
    assert exec_lines == [
        "exec uv run --directory packages/garmin-mcp-server garmin-mcp-server"
    ]
