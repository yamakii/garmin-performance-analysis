"""Anti-staleness guard: the legacy section analysts are gone (Issue #1256).

``run_note`` is the only section an agent writes. Docs, rules, skills and
workflows are normative text that people and agents follow, so a surviving
mention of a deleted analyst would send a reader to an agent that no longer
exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.utils.paths import get_project_root

_LEGACY_ANALYSTS = (
    "unified-section-analyst",
    "summary-section-analyst",
    "split-section-analyst",
)

# Trees whose text is read as instructions (docs, rules, skills, workflows).
_SCANNED_DIRS = ("docs", ".claude/agents", ".claude/rules", ".claude/skills")
_SCANNED_FILES = ("CLAUDE.md", "README.md")


def _text_files(root: Path) -> list[Path]:
    files = [root / name for name in _SCANNED_FILES]
    for directory in _SCANNED_DIRS:
        files.extend(sorted((root / directory).rglob("*.md")))
    workflows = root / ".claude" / "workflows"
    files.extend(sorted(p for p in workflows.rglob("*") if p.is_file()))
    return [p for p in files if p.is_file()]


@pytest.mark.unit
def test_no_legacy_analyst_is_referenced() -> None:
    root = get_project_root()

    offenders: list[str] = []
    for path in _text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for analyst in _LEGACY_ANALYSTS:
            if analyst in text:
                offenders.append(f"{path.relative_to(root)}: {analyst}")

    assert not offenders, f"legacy analyst references: {offenders}"

    leftovers = sorted(p.name for p in (root / ".claude" / "agents").glob("*.md"))
    assert not [n for n in leftovers if n.endswith("-section-analyst.md")], leftovers
