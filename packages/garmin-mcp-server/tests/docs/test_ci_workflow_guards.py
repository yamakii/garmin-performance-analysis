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


def _filter_block(text: str, name: str) -> str:
    """Return the entries of one paths-filter list (``code:``, ``docs:`` ...)."""
    filters = re.search(r"filters:\s*\|\n((?:[ \t]+.*\n)+)", text)
    assert filters, "paths-filter `filters:` block not found"
    block = re.search(
        rf"^\s+{name}:\n((?:\s+-.*\n|\s+#.*\n)+)", filters.group(1), re.MULTILINE
    )
    assert block, f"`{name}:` filter not found"
    return block.group(1)


@pytest.mark.unit
def test_ci_code_filter_excludes_docs() -> None:
    """A docs-only PR must not pay for the whole lint-and-test job (#1060)."""
    text = _CI_YML.read_text(encoding="utf-8")
    code_block = _filter_block(text, "code")
    assert "'docs/**'" not in code_block
    assert "'**/*.md'" not in code_block
    assert "'.env.example'" not in code_block


@pytest.mark.unit
def test_ci_docs_guard_job_gates_ci_guard() -> None:
    """Docs/rules/markdown changes run tests/docs via docs-guard and gate ci-guard."""
    text = _CI_YML.read_text(encoding="utf-8")
    docs_block = _filter_block(text, "docs")
    for entry in ("'docs/**'", "'**/*.md'", "'.claude/**'", "'.nvmrc'"):
        assert entry in docs_block, f"{entry} missing from `docs:` filter"
    assert "docs: ${{ steps.filter.outputs.docs }}" in text
    assert re.search(r"^  docs-guard:\n", text, re.MULTILINE), "docs-guard job"
    assert "pytest tests/docs -n 0" in text
    guard_needs = re.search(
        r"^  ci-guard:\n\s+needs:\s*\[([^\]]+)\]", text, re.MULTILINE
    )
    assert guard_needs and "docs-guard" in guard_needs.group(1)
    assert "needs.docs-guard.result" in text


@pytest.mark.unit
def test_ci_concurrency_cancels_superseded_runs() -> None:
    """A re-push cancels the PR run it supersedes; main runs key on the SHA."""
    text = _CI_YML.read_text(encoding="utf-8")
    concurrency = _top_level_block(text, "concurrency")
    assert re.search(r"cancel-in-progress:\s*true", concurrency)
    assert "github.event.pull_request.number || github.sha" in concurrency


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
def test_ci_docker_filter_and_job_present() -> None:
    """A docker/** change must build the sandbox image and gate ci-guard on it."""
    text = _CI_YML.read_text(encoding="utf-8")
    filters = re.search(r"filters:\s*\|\n((?:[ \t]+.*\n)+)", text)
    assert filters, "paths-filter `filters:` block not found"
    docker_block = re.search(
        r"^\s+docker:\n((?:\s+-.*\n|\s+#.*\n)+)", filters.group(1), re.MULTILINE
    )
    assert docker_block, "`docker:` filter not found"
    assert "'docker/**'" in docker_block.group(1)
    # The filter result must be exported, or `needs.changes.outputs.docker`
    # is always empty and the job silently never runs.
    assert "docker: ${{ steps.filter.outputs.docker }}" in text
    assert re.search(r"^  docker-build:\n", text, re.MULTILINE), "docker-build job"
    assert "docker build" in text
    guard_needs = re.search(
        r"^  ci-guard:\n\s+needs:\s*\[([^\]]+)\]", text, re.MULTILINE
    )
    assert guard_needs and "docker-build" in guard_needs.group(1)
    assert "needs.docker-build.result" in text


@pytest.mark.unit
def test_security_audit_scans_both_lockfiles() -> None:
    """The weekly audit covers uv.lock (pip-audit) and the frontend lock (npm audit)."""
    text = _SECURITY_AUDIT_YML.read_text(encoding="utf-8")
    assert "pip-audit" in text
    assert "npm audit --audit-level=high" in text
    assert "schedule:" in text and "workflow_dispatch:" in text
    # The reporting job needs to write issues; nothing else should.
    assert text.count("issues: write") == 1
