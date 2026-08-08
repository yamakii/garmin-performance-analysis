"""Regression guard for the repo's `.claude` ignore patterns (#882).

A gitignore pattern that contains a slash is anchored to the directory holding
the `.gitignore`, so the bare `.claude/settings.local.json` form only ever
matched the repo root and left `packages/*/.claude/` local settings showing as
untracked. These tests assert the real `git check-ignore` behaviour rather than
the file's text, so they fail if the pattern is narrowed again -- and equally if
it is widened enough to swallow the tracked `.claude` assets.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# tests/docs/test_gitignore_patterns.py -> packages/garmin-mcp-server -> packages -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _is_ignored(relative_path: str) -> bool:
    """Return whether git would ignore ``relative_path`` (need not exist on disk)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", relative_path],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    # 0 = ignored, 1 = not ignored, anything else = git itself failed.
    assert result.returncode in (0, 1), (
        f"git check-ignore failed for {relative_path!r}: "
        f"rc={result.returncode} stderr={result.stderr.decode(errors='replace')}"
    )
    return result.returncode == 0


@pytest.mark.unit
def test_root_claude_local_settings_ignored() -> None:
    """The repo-root local settings file stays ignored."""
    assert _is_ignored(".claude/settings.local.json")


@pytest.mark.unit
def test_nested_claude_local_settings_ignored() -> None:
    """Local settings under a package are ignored too (the #882 regression)."""
    assert _is_ignored("packages/garmin-mcp-server/.claude/settings.local.json")


@pytest.mark.unit
def test_nested_claude_tasks_ignored() -> None:
    """Session task scratch files under a package are ignored."""
    assert _is_ignored("packages/garmin-web/.claude/tasks/todo.md")


@pytest.mark.unit
def test_nested_claude_worktrees_ignored() -> None:
    """Worktree checkouts under a package are ignored."""
    assert _is_ignored("packages/garmin-web/.claude/worktrees/wt/file.txt")


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        ".claude/agents/developer.md",
        ".claude/skills/implement/SKILL.md",
        ".claude/rules/dev/dev-reference.md",
        ".claude/workflows/implement-tier.js",
        "packages/garmin-mcp-server/.claude/agents/some-agent.md",
    ],
)
def test_tracked_claude_assets_not_ignored(path: str) -> None:
    """Widening the patterns must not swallow tracked .claude assets."""
    assert not _is_ignored(path)
