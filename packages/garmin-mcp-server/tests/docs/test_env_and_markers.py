"""Anti-staleness guards for ``.env.example`` and pytest markers.

Keeps two more code-derived facts honest:

- every ``GARMIN_*`` env var the code reads via ``os.getenv(...)`` /
  ``os.environ[...]`` is documented in ``.env.example``, and
- the pytest marker table in ``docs/testing_guidelines.md`` matches the markers
  declared in ``packages/garmin-mcp-server/pyproject.toml``.

Catches the drift seen this session (missing ``slow`` marker; auth env vars
absent from ``.env.example``).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

# packages/garmin-mcp-server/tests/docs/<this file> -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC_ROOT = _REPO_ROOT / "packages" / "garmin-mcp-server" / "src"
_PYPROJECT = _REPO_ROOT / "packages" / "garmin-mcp-server" / "pyproject.toml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_TESTING_DOC = _REPO_ROOT / "docs" / "testing_guidelines.md"

# GARMIN_* env vars that are intentionally not documented in .env.example.
ENV_VAR_ALLOWLIST: frozenset[str] = frozenset()

# os.getenv("GARMIN_X") | os.environ.get("GARMIN_X") | os.environ["GARMIN_X"]
_ENV_READ_RE = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["'](GARMIN_[A-Z0-9_]+)["']"""
    r"""|os\.environ\[\s*["'](GARMIN_[A-Z0-9_]+)["']\s*\]"""
)

# Markdown table row: first cell may wrap the marker in backticks.
_MARKER_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")


def discover_env_vars(src_root: Path) -> set[str]:
    """Collect ``GARMIN_*`` env var names read across ``src_root``.

    Scans ``*.py`` files for ``os.getenv(...)`` / ``os.environ.get(...)`` /
    ``os.environ[...]`` reads of names matching ``GARMIN_*`` (underscore after
    the prefix; e.g. ``GARMINTOKENS`` is excluded by design).
    """
    found: set[str] = set()
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in _ENV_READ_RE.finditer(text):
            found.add(m.group(1) or m.group(2))
    return found


def declared_markers(pyproject: Path) -> set[str]:
    """Return the pytest marker names declared in ``pyproject``.

    Parses ``[tool.pytest.ini_options].markers`` (list of ``"name: desc"``)
    and returns the bare names.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    markers = data["tool"]["pytest"]["ini_options"]["markers"]
    return {entry.split(":", 1)[0].strip() for entry in markers}


def documented_markers(doc: Path) -> set[str]:
    """Return the marker names documented in the marker table of ``doc``.

    Parses markdown table rows whose first cell is a backtick-wrapped marker
    name (e.g. ``| `unit` | ... |``).
    """
    found: set[str] = set()
    for line in doc.read_text(encoding="utf-8").splitlines():
        m = _MARKER_ROW_RE.match(line.strip())
        if m:
            found.add(m.group(1))
    return found


# --- discover_env_vars() ----------------------------------------------------


@pytest.mark.unit
def test_discover_env_vars_finds_known(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text(
        'import os\nx = os.getenv("GARMIN_EMAIL")\n',
        encoding="utf-8",
    )
    assert "GARMIN_EMAIL" in discover_env_vars(src)


# --- guards over real files -------------------------------------------------


@pytest.mark.unit
def test_env_example_documents_all_garmin_vars():
    discovered = discover_env_vars(_SRC_ROOT) - ENV_VAR_ALLOWLIST
    assert discovered, "expected to discover at least one GARMIN_* env var"
    env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    missing = sorted(name for name in discovered if name not in env_text)
    assert not missing, (
        "GARMIN_* env vars read in code but not documented in .env.example: "
        + ", ".join(missing)
    )


@pytest.mark.unit
def test_documented_markers_match_pyproject():
    declared = declared_markers(_PYPROJECT)
    documented = documented_markers(_TESTING_DOC)
    assert "slow" in declared
    assert documented == declared, (
        "marker table in testing_guidelines.md is out of sync with "
        f"pyproject.toml. declared={sorted(declared)} "
        f"documented={sorted(documented)}"
    )
