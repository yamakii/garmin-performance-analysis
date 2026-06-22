"""Documentation reference-integrity guard.

Scans ``README.md``, ``CLAUDE.md``, and ``docs/**/*.md`` and fails when a doc
references something that does not exist:

- a broken relative markdown link, or
- a referenced repo path (inline-code token starting with a known prefix).

Catches the failure modes from the 2026-06-20 audit (``tools.utils.paths``,
dead links, phantom file references).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from garmin_mcp.utils.paths import get_project_root

# Inline-code tokens whose existence is intentionally not asserted (examples,
# generated paths, or files that legitimately may not exist on disk).
REPO_PATH_ALLOWLIST: frozenset[str] = frozenset()

# Repo-path prefixes we treat as "this should exist on disk".
_REPO_PATH_PREFIXES = ("packages/", ".claude/", "docs/", "scripts/")

# Markdown link: [text](target)
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Inline-code span: `...`  (single-backtick, non-greedy, no embedded backtick)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

# Fenced code block: ``` ... ``` or ~~~ ... ~~~
_FENCE_RE = re.compile(r"^(```|~~~)")


def _iter_doc_files(root: Path) -> list[Path]:
    """Collect doc files: README.md, CLAUDE.md, and docs/**/*.md."""
    files: list[Path] = []
    for name in ("README.md", "CLAUDE.md"):
        candidate = root / name
        if candidate.exists():
            files.append(candidate)
    docs_dir = root / "docs"
    if docs_dir.exists():
        files.extend(sorted(docs_dir.rglob("*.md")))
    return files


def _strip_fenced_code(markdown: str) -> str:
    """Remove fenced-code-block contents to avoid example noise."""
    out: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE_RE.match(line.lstrip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _relative_links(markdown: str) -> list[str]:
    """Extract local relative link targets (anchors stripped).

    Skips ``http(s)://``, ``mailto:``, and anchor-only ``#...`` targets.
    A trailing ``#anchor`` is removed from otherwise-local targets.
    """
    body = _strip_fenced_code(markdown)
    results: list[str] = []
    for raw in _LINK_RE.findall(body):
        target = raw.strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            continue
        # Strip anchor fragment.
        path_part = target.split("#", 1)[0].strip()
        if not path_part:
            continue
        results.append(path_part)
    return results


def _repo_path_tokens(markdown: str) -> list[str]:
    """Extract inline-code tokens that look like real repo paths.

    Matches tokens starting with a known prefix (``packages/``, ``.claude/``,
    ``docs/``, ``scripts/``). Conservatively skips tokens with spaces, ``<``,
    ``>``, ``*`` (incl. glob ``**``), or placeholders ``{...}`` to avoid false
    positives.
    """
    body = _strip_fenced_code(markdown)
    results: list[str] = []
    for token in _INLINE_CODE_RE.findall(body):
        token = token.strip()
        if not token.startswith(_REPO_PATH_PREFIXES):
            continue
        if any(ch in token for ch in (" ", "\t", "<", ">", "*", "{", "}")):
            continue
        results.append(token)
    return results


def _docs_with_content() -> list[tuple[Path, str]]:
    root = get_project_root()
    return [(p, p.read_text(encoding="utf-8")) for p in _iter_doc_files(root)]


# --- _relative_links() ------------------------------------------------------


@pytest.mark.unit
def test_relative_links_extracts_local_only():
    markdown = "[a](docs/x.md) and [b](https://e.com) and [c](#sec)"
    assert _relative_links(markdown) == ["docs/x.md"]


@pytest.mark.unit
def test_relative_links_strips_anchor():
    markdown = "see [a](docs/x.md#sec)"
    assert _relative_links(markdown) == ["docs/x.md"]


# --- _repo_path_tokens() ----------------------------------------------------


@pytest.mark.unit
def test_repo_path_tokens_matches_known_prefixes():
    markdown = "run `packages/foo.py` then `scripts/ci-check.sh`"
    assert _repo_path_tokens(markdown) == [
        "packages/foo.py",
        "scripts/ci-check.sh",
    ]


@pytest.mark.unit
def test_repo_path_tokens_skips_placeholders():
    markdown = "edit `packages/{id}/x` or `a b`"
    assert _repo_path_tokens(markdown) == []


# --- guard over real docs ---------------------------------------------------


@pytest.mark.unit
def test_all_docs_links_resolve():
    missing: list[str] = []
    for doc_path, content in _docs_with_content():
        for link in _relative_links(content):
            resolved = (doc_path.parent / link).resolve()
            if not resolved.exists():
                missing.append(f"{doc_path}: {link}")
    assert not missing, "Broken relative links:\n" + "\n".join(missing)


@pytest.mark.unit
def test_all_referenced_repo_paths_exist():
    root = get_project_root()
    missing: list[str] = []
    for doc_path, content in _docs_with_content():
        for token in _repo_path_tokens(content):
            if token in REPO_PATH_ALLOWLIST:
                continue
            if not (root / token).exists():
                missing.append(f"{doc_path}: {token}")
    assert not missing, "Referenced repo paths that do not exist:\n" + "\n".join(
        missing
    )


# --- reload model wording guard (Issue #482) --------------------------------

# Docs/rules that must describe the *new* shim+worker reload model (Epic #478),
# not the retired "self-exit + client respawn" one. Resolved relative to the
# repo root so the guard is path-portable across worktrees.
_RELOAD_MODEL_DOCS: tuple[str, ...] = (
    "docs/architecture.md",
    ".claude/rules/dev/worktree-validation-protocol.md",
    ".claude/rules/dev/dev-reference.md",
)

# Patterns signalling the stale (pre-#478) reload prescription.
_STALE_RELOAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"os\._exit"),
    re.compile(r"自動的に再接続"),
    re.compile(r"自動 ?respawn|automatically (?:respawn|reconnect)"),
    re.compile(r"reload_server\(server_dir"),
)

# A stale match is allowed only when the line also marks it as the *removed*
# old model (so explaining what was retired is fine; prescribing it is not).
_REMOVED_MARKERS: re.Pattern[str] = re.compile(
    r"撤去|削除|廃止|旧|\bold\b|retired|removed|no longer|もはや|"
    r"かつて|previously|\bgone\b"
)


@pytest.mark.unit
def test_docs_no_stale_reload_self_exit_wording():
    """Guard: reload docs must not prescribe the retired self-exit/respawn model.

    The new model (Epic #478) is a stable shim + swappable worker where
    ``reload_server`` restarts only the worker and the shim/session survives.
    The retired model killed the process (``os._exit``), relied on the client to
    automatically respawn/reconnect, and pointed reload at a ``server_dir``.
    Mentions that explicitly describe the old model as removed are allowed.
    """
    root = get_project_root()
    offenders: list[str] = []
    for rel in _RELOAD_MODEL_DOCS:
        path = root / rel
        assert path.exists(), f"{rel} missing (reload-model doc moved?)"
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for pat in _STALE_RELOAD_PATTERNS:
                if pat.search(line) and not _REMOVED_MARKERS.search(line):
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Stale reload-model wording (pre-#478 self-exit/respawn) found. "
        "Describe the shim+worker model instead, or mark the mention as the "
        "removed old model:\n" + "\n".join(offenders)
    )
