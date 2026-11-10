"""Byte budget for the text that shapes the coach (Epic #1544, Phase 3).

Coaching rules grew by one loop: an incident, a sentence appended to the text
the LLM reads, nothing removed. ``.claude/rule-budget.json`` caps each layer of
that text so "add only by removing" is checked mechanically:

- a layer over its ceiling fails (adding needs a matching removal);
- a ceiling more than ``max_headroom_bytes`` above the layer fails too, so a
  removal also lowers the ceiling (a downward-only ratchet; ``--write`` resets
  every ceiling to the current size plus ``slack_bytes``).

Raising a ceiling is an owner decision recorded in the PR
(``.claude/rules/dev/coach-incident-protocol.md``).

Layer kinds:

- ``unscoped_rules``: CLAUDE.md plus every ``.claude/rules/**/*.md`` without a
  ``paths:`` frontmatter block (loaded into every session);
- ``files``: the summed size of the listed files;
- ``contract``: the JSON of ``get_contract(section)``, i.e. what the agent reads,
  measured by executing that ``contracts.py`` source in isolation so past
  commits can be measured too.

Usage:
    uv run python -m garmin_mcp.scripts.rule_budget            # --check
    uv run python -m garmin_mcp.scripts.rule_budget --write
    uv run python -m garmin_mcp.scripts.rule_budget --history --since 2026-10-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

BUDGET_FILE = ".claude/rule-budget.json"

# scripts/rule_budget.py -> garmin_mcp -> src -> garmin-mcp-server -> packages -> repo root
_DEFAULT_ROOT = Path(__file__).resolve().parents[4]


class Source:
    """Read repository text either from the working tree or from a git commit."""

    def __init__(self, root: Path, commit: str | None = None) -> None:
        self.root = root
        self.commit = commit

    def read(self, rel: str) -> str | None:
        """Return the file's text, or None when it does not exist."""
        if self.commit is None:
            p = self.root / rel
            return p.read_text(encoding="utf-8") if p.is_file() else None
        r = subprocess.run(
            ["git", "show", f"{self.commit}:{rel}"],
            cwd=self.root,
            capture_output=True,
        )
        return r.stdout.decode("utf-8") if r.returncode == 0 else None

    def list_md(self, rel_dir: str) -> list[str]:
        """Return every ``*.md`` path under ``rel_dir`` (repo-relative, sorted)."""
        if self.commit is None:
            base = self.root / rel_dir
            if not base.is_dir():
                return []
            return sorted(str(p.relative_to(self.root)) for p in base.rglob("*.md"))
        r = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", self.commit, "--", rel_dir],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return sorted(line for line in r.stdout.splitlines() if line.endswith(".md"))


def has_paths_frontmatter(text: str) -> bool:
    """Return whether ``text`` opens with a frontmatter block containing ``paths:``."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return False
    for line in lines[1:]:
        if line == "---":
            return False
        if line.startswith("paths:"):
            return True
    return False


def _nbytes(text: str | None) -> int:
    return len(text.encode("utf-8")) if text is not None else 0


def contract_bytes(source_text: str, section: str) -> int:
    """Size of ``get_contract(section)`` as JSON, from a ``contracts.py`` source text."""
    namespace: dict[str, Any] = {"__name__": "_rule_budget_contracts"}
    exec(
        compile(source_text, "contracts.py", "exec"), namespace
    )  # noqa: S102 - repo-owned source
    contract = namespace["get_contract"](section)
    return _nbytes(json.dumps(contract, ensure_ascii=False))


def measure_layer(src: Source, layer: dict[str, Any]) -> int | None:
    """Return a layer's current size in bytes, or None when it cannot be measured."""
    kind = layer["kind"]
    if kind == "files":
        return sum(_nbytes(src.read(p)) for p in layer["paths"])
    if kind == "unscoped_rules":
        total = _nbytes(src.read("CLAUDE.md"))
        for rel in src.list_md(".claude/rules"):
            text = src.read(rel)
            if text is not None and not has_paths_frontmatter(text):
                total += _nbytes(text)
        return total
    if kind == "contract":
        text = src.read(layer["path"])
        if text is None:
            return None
        try:
            return contract_bytes(text, layer["section"])
        except Exception:  # a past commit's contract may not have had this shape
            return None
    raise ValueError(f"unknown layer kind: {kind}")


def load_budget(root: Path) -> dict[str, Any]:
    budget: dict[str, Any] = json.loads(
        (root / BUDGET_FILE).read_text(encoding="utf-8")
    )
    return budget


def check(root: Path, out: Callable[[str], None] = print) -> list[str]:
    """Check every layer against its ceiling. Returns the failure messages."""
    budget = load_budget(root)
    slack = budget["slack_bytes"]
    headroom = budget["max_headroom_bytes"]
    src = Source(root)
    failures: list[str] = []
    for name, layer in budget["layers"].items():
        size = measure_layer(src, layer)
        ceiling = layer["ceiling_bytes"]
        if size is None:
            failures.append(f"{name}: could not be measured")
        elif size > ceiling:
            failures.append(
                f"{name}: {size} bytes > ceiling {ceiling}. Add only by removing: "
                "merge or delete as much as you add (coach-incident-protocol.md)."
            )
        elif ceiling - size > headroom:
            failures.append(
                f"{name}: ceiling {ceiling} is {ceiling - size} bytes above the layer ({size}). "
                f"Lower it to {size + slack} (run rule_budget --write) so the removal sticks."
            )
        else:
            out(f"  ok: {name}: {size} / {ceiling} bytes")
    for f in failures:
        out(f"  FAIL: {f}")
    return failures


def write(root: Path, out: Callable[[str], None] = print) -> None:
    """Reset every ceiling to the layer's current size plus ``slack_bytes``."""
    budget = load_budget(root)
    src = Source(root)
    for name, layer in budget["layers"].items():
        size = measure_layer(src, layer)
        if size is None:
            raise SystemExit(f"{name}: could not be measured")
        layer["ceiling_bytes"] = size + budget["slack_bytes"]
        out(f"  {name}: ceiling -> {layer['ceiling_bytes']}")
    (root / BUDGET_FILE).write_text(
        json.dumps(budget, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def measure_at(
    root: Path, commit: str, layers: dict[str, Any]
) -> dict[str, int | None]:
    """Measure every layer at ``commit`` (the layer definitions come from today's budget)."""
    src = Source(root, commit)
    return {name: measure_layer(src, layer) for name, layer in layers.items()}


def history(
    root: Path, since: dt.date, ref: str = "HEAD", out: Callable[[str], None] = print
) -> None:
    """Print each layer's size at the last commit before every Monday since ``since``."""
    layers = load_budget(root)["layers"]
    names = list(layers)
    out("| week | commit | " + " | ".join(names) + " |")
    out("|" + " --- |" * (len(names) + 2))
    day = since - dt.timedelta(days=since.weekday())
    end = dt.date.today() + dt.timedelta(days=7)
    while day <= end:
        r = subprocess.run(
            ["git", "rev-list", "-1", f"--before={day.isoformat()} 00:00", ref],
            cwd=root,
            capture_output=True,
            text=True,
        )
        commit = r.stdout.strip()
        if commit:
            sizes = measure_at(root, commit, layers)
            cells = ["-" if sizes[n] is None else str(sizes[n]) for n in names]
            out(f"| {day.isoformat()} | {commit[:7]} | " + " | ".join(cells) + " |")
        day += dt.timedelta(days=7)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="reset ceilings to current + slack"
    )
    mode.add_argument(
        "--history", action="store_true", help="weekly layer sizes from git history"
    )
    parser.add_argument(
        "--since", type=dt.date.fromisoformat, default=dt.date(2026, 10, 1)
    )
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    args = parser.parse_args(argv)
    if args.write:
        write(args.root)
        return 0
    if args.history:
        history(args.root, args.since, args.ref)
        return 0
    return 1 if check(args.root) else 0


if __name__ == "__main__":
    sys.exit(main())
