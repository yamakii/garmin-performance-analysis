"""Byte budget for the coach-shaping text (Epic #1544, #1556).

The repo check lives in tests/docs so it runs both for docs-only PRs (rules,
skills, agents: the docs-guard job) and for code PRs (the contract: the full
suite). The rest exercises the ratchet on a throwaway root.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import garmin_mcp.scripts.rule_budget as rule_budget
from garmin_mcp.validation.contracts import get_contract

# tests/docs/test_rule_budget.py -> packages/garmin-mcp-server -> packages -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]

_CONTRACT_SRC = (
    "from typing import Any\n"
    "_C: dict[str, Any] = {'run_note': {'rule': 'x' * 100}}\n"
    "def get_contract(section_type: str) -> dict[str, Any]:\n"
    "    return _C[section_type]\n"
)


def _make_root(tmp_path: Path) -> Path:
    """A minimal repo with one file per layer kind and a budget sized to it."""
    files = {
        "CLAUDE.md": "# overview\n",
        ".claude/rules/general.md": "always loaded\n",
        ".claude/rules/dev/scoped.md": "---\npaths:\n  - 'x/**'\n---\nscoped\n",
        ".claude/agents/run-note-analyst.md": "a" * 500,
        ".claude/skills/coach/SKILL.md": "s" * 1000,
        "contracts.py": _CONTRACT_SRC,
    }
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    budget = {
        "slack_bytes": 1024,
        "max_headroom_bytes": 2048,
        "layers": {
            "always_loaded": {"kind": "unscoped_rules", "ceiling_bytes": 0},
            "run_note_contract": {
                "kind": "contract",
                "path": "contracts.py",
                "section": "run_note",
                "ceiling_bytes": 0,
            },
            "run_note_agent": {
                "kind": "files",
                "paths": [".claude/agents/run-note-analyst.md"],
                "ceiling_bytes": 0,
            },
            "coach_skills": {
                "kind": "files",
                "paths": [".claude/skills/coach/SKILL.md"],
                "ceiling_bytes": 0,
            },
        },
    }
    (tmp_path / rule_budget.BUDGET_FILE).write_text(
        json.dumps(budget), encoding="utf-8"
    )
    rule_budget.write(tmp_path, out=lambda _: None)
    return tmp_path


def _ceiling(root: Path, layer: str) -> int:
    return int(rule_budget.load_budget(root)["layers"][layer]["ceiling_bytes"])


@pytest.mark.unit
def test_check_passes_on_repo() -> None:
    """The repository's coach layers sit within their ceilings, with no stale headroom."""
    failures = rule_budget.check(_REPO_ROOT, out=lambda _: None)
    assert failures == [], "\n".join(failures)


@pytest.mark.unit
def test_default_root_is_repo_root() -> None:
    """The documented command (no --root) finds .claude/rule-budget.json."""
    assert rule_budget._DEFAULT_ROOT == _REPO_ROOT
    assert rule_budget.main([]) == 0


@pytest.mark.unit
def test_check_fails_over_ceiling(tmp_path: Path) -> None:
    """Adding 2 KB to a skill without removing anything fails coach_skills."""
    root = _make_root(tmp_path)
    assert rule_budget.check(root, out=lambda _: None) == []
    skill = root / ".claude/skills/coach/SKILL.md"
    skill.write_text(skill.read_text() + "n" * 2048, encoding="utf-8")
    failures = rule_budget.check(root, out=lambda _: None)
    assert len(failures) == 1
    assert failures[0].startswith("coach_skills:")
    assert "Add only by removing" in failures[0]


@pytest.mark.unit
def test_check_fails_on_stale_headroom(tmp_path: Path) -> None:
    """A ceiling 3,000 B above the layer fails and names the ceiling to lower to."""
    root = _make_root(tmp_path)
    budget = rule_budget.load_budget(root)
    budget["layers"]["run_note_agent"]["ceiling_bytes"] = 500 + 3000
    (root / rule_budget.BUDGET_FILE).write_text(json.dumps(budget), encoding="utf-8")
    failures = rule_budget.check(root, out=lambda _: None)
    assert len(failures) == 1
    assert failures[0].startswith("run_note_agent:")
    assert "Lower it to 1524" in failures[0]


@pytest.mark.unit
def test_write_sets_ceiling_to_current_plus_slack(tmp_path: Path) -> None:
    """--write sets every ceiling to the measured size plus slack_bytes."""
    root = _make_root(tmp_path)
    assert _ceiling(root, "run_note_agent") == 500 + 1024
    assert _ceiling(root, "coach_skills") == 1000 + 1024
    # CLAUDE.md + the unscoped rule; the dev rule with paths: is not counted.
    assert (
        _ceiling(root, "always_loaded")
        == len("# overview\n") + len("always loaded\n") + 1024
    )


@pytest.mark.unit
def test_write_never_raises_a_ceiling(tmp_path: Path) -> None:
    """--write only lowers: a layer that grew keeps its ceiling (owner decision)."""
    root = _make_root(tmp_path)
    skill = root / ".claude/skills/coach/SKILL.md"
    skill.write_text(skill.read_text() + "n" * 500, encoding="utf-8")
    rule_budget.write(root, out=lambda _: None)
    assert _ceiling(root, "coach_skills") == 1000 + 1024


@pytest.mark.unit
def test_contract_size_from_source_matches_import() -> None:
    """Executing contracts.py in isolation measures exactly what get_contract returns."""
    src = (
        _REPO_ROOT / "packages/garmin-mcp-server/src/garmin_mcp/validation/contracts.py"
    ).read_text(encoding="utf-8")
    expected = len(
        json.dumps(get_contract("run_note"), ensure_ascii=False).encode("utf-8")
    )
    assert rule_budget.contract_bytes(src, "run_note") == expected


@pytest.mark.unit
def test_history_measures_past_commit(tmp_path: Path) -> None:
    """measure_at reads a layer as it was at an older commit, not as it is now."""
    root = _make_root(tmp_path)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    first = git("rev-parse", "HEAD")
    (root / ".claude/agents/run-note-analyst.md").write_text(
        "a" * 800, encoding="utf-8"
    )
    git("commit", "-q", "-am", "two")

    layers = rule_budget.load_budget(root)["layers"]
    assert rule_budget.measure_at(root, first, layers)["run_note_agent"] == 500
    assert rule_budget.measure_at(root, "HEAD", layers)["run_note_agent"] == 800
    assert rule_budget.measure_at(root, first, layers)["run_note_contract"] == len(
        json.dumps({"rule": "x" * 100}).encode()
    )
