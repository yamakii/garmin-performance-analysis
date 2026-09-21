"""Guard: the developer agent definition states, and obeys, the command rules.

A developer subagent that reads and edits files through ``cd <worktree> && sed``
costs the owner one permission prompt per step (#1292). The definition is the
only place the agent learns the rule from, so it must both say it and not
contradict it in its own examples.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFINITION = REPO_ROOT / ".claude" / "agents" / "developer.md"

SECTION_HEADING = "## コマンドの打ち方"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = re.search(r"^## ", text[start + len(heading) :], flags=re.MULTILINE)
    end = start + len(heading) + following.start() if following else len(text)
    return text[start:end]


def _bash_lines(text: str) -> list[str]:
    lines: list[str] = []
    for block in re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL):
        lines.extend(line.strip() for line in block.splitlines() if line.strip())
    return lines


@pytest.mark.unit
def test_developer_agent_states_the_command_rules() -> None:
    section = _section(DEFINITION.read_text(encoding="utf-8"), SECTION_HEADING)

    for token in ("Read", "Edit", "Write", "Grep", "git -C", "uv run --directory"):
        assert token in section, token
    # Routing around a denied command is named and forbidden.
    assert "拒否" in section
    assert "迂回" in section


@pytest.mark.unit
def test_developer_agent_examples_obey_the_command_rules() -> None:
    lines = _bash_lines(DEFINITION.read_text(encoding="utf-8"))

    assert lines, "the definition has bash examples to check"
    for line in lines:
        assert not line.startswith("cd "), line
        assert "sed -i" not in line, line
        assert "<<" not in line, line
        assert "python -c" not in line, line
        if line.startswith("git "):
            assert line.startswith("git -C "), line
