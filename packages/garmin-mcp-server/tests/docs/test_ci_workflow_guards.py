"""Guards for the maintenance automation wiring (#941).

These assert the properties that make dependency updates safe to auto-merge:

* ``ci.yml`` runs with a read-only ``GITHUB_TOKEN`` and treats a lockfile-only
  change as a code change (otherwise a Dependabot bump of ``uv.lock`` would
  skip ``lint-and-test`` and ``ci-guard`` would pass vacuously).
* ``dependabot.yml`` covers every ecosystem the repo actually depends on, so a
  newly added manifest is not silently left unmanaged.

The workflow files are plain text here (no YAML parser in the test deps), so the
checks are deliberately structural rather than semantic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/docs/<file> -> packages/garmin-mcp-server -> packages -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_DEPENDABOT_YML = _REPO_ROOT / ".github" / "dependabot.yml"
_SECURITY_AUDIT_YML = _REPO_ROOT / ".github" / "workflows" / "security-audit.yml"


def _top_level_block(text: str, key: str) -> str:
    """Return the text of a top-level ``key:`` mapping (up to the next top-level key)."""
    match = re.search(rf"^{re.escape(key)}:\n((?:[ \t]+.*\n|\n)*)", text, re.MULTILINE)
    assert match, f"top-level `{key}:` block not found"
    return match.group(1)


@pytest.mark.unit
def test_ci_yml_has_least_privilege_permissions() -> None:
    """ci.yml declares a read-only token at workflow level."""
    text = _CI_YML.read_text(encoding="utf-8")
    permissions = _top_level_block(text, "permissions")
    assert re.search(r"^\s+contents:\s*read\s*$", permissions, re.MULTILINE)
    assert "write" not in permissions


@pytest.mark.unit
def test_ci_changes_filter_includes_uv_lock() -> None:
    """A lockfile-only PR must trigger lint-and-test via the `code` filter."""
    text = _CI_YML.read_text(encoding="utf-8")
    filters = re.search(r"filters:\s*\|\n((?:[ \t]+.*\n)+)", text)
    assert filters, "paths-filter `filters:` block not found"
    code_block = re.search(
        r"^\s+code:\n((?:\s+-.*\n|\s+#.*\n)+)", filters.group(1), re.MULTILINE
    )
    assert code_block, "`code:` filter not found"
    assert "'uv.lock'" in code_block.group(1)
    assert "'packages/**'" in code_block.group(1)


@pytest.mark.unit
def test_dependabot_covers_all_ecosystems() -> None:
    """Every manifest type in the repo has a Dependabot entry."""
    text = _DEPENDABOT_YML.read_text(encoding="utf-8")
    ecosystems = set(re.findall(r'package-ecosystem:\s*"([^"]+)"', text))
    assert ecosystems == {"uv", "npm", "github-actions", "docker"}
    # The npm entry must point at the frontend, where package-lock.json lives.
    assert '"/packages/garmin-web/frontend"' in text
    assert (_REPO_ROOT / "packages/garmin-web/frontend/package-lock.json").exists()
    assert (_REPO_ROOT / "uv.lock").exists()
    assert (_REPO_ROOT / "docker/Dockerfile").exists()


@pytest.mark.unit
def test_security_audit_scans_both_lockfiles() -> None:
    """The weekly audit covers uv.lock (pip-audit) and the frontend lock (npm audit)."""
    text = _SECURITY_AUDIT_YML.read_text(encoding="utf-8")
    assert "pip-audit" in text
    assert "npm audit --audit-level=high" in text
    assert "schedule:" in text and "workflow_dispatch:" in text
    # The reporting job needs to write issues; nothing else should.
    assert text.count("issues: write") == 1
