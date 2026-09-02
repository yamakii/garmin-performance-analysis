"""Guard: the Node runtime version is declared in one place per consumer and
they must agree (#952).

`.nvmrc` drives CI (`actions/setup-node` reads it); `docker/Dockerfile`
installs NodeSource `setup_<NODE_MAJOR>.x` for the sandbox image; the frontend
`package.json` `engines.node` floor tells npm what the app expects. A bump that
touches only one of them leaves CI and the sandbox on different majors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# tests/docs/<file> -> packages/garmin-mcp-server -> packages -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_NVMRC = _REPO_ROOT / ".nvmrc"
_DOCKERFILE = _REPO_ROOT / "docker" / "Dockerfile"
_FRONTEND_PACKAGE_JSON = _REPO_ROOT / "packages/garmin-web/frontend/package.json"


def _nvmrc_major() -> int:
    return int(_NVMRC.read_text(encoding="utf-8").strip().lstrip("v").split(".")[0])


@pytest.mark.unit
def test_nvmrc_matches_dockerfile_node_major() -> None:
    """`.nvmrc` and the Dockerfile's `ARG NODE_MAJOR` name the same major."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"^ARG NODE_MAJOR=(\d+)\s*$", text, re.MULTILINE)
    assert match, "ARG NODE_MAJOR=<n> not found in docker/Dockerfile"
    assert int(match.group(1)) == _nvmrc_major() == 24


@pytest.mark.unit
def test_engines_node_floor_matches_nvmrc() -> None:
    """The frontend's `engines.node` floor is the `.nvmrc` major (no stale lower range)."""
    pkg = json.loads(_FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    engines = pkg["engines"]["node"]
    match = re.fullmatch(r">=(\d+)\.\d+\.\d+", engines)
    assert match, f"engines.node should be a single '>=X.Y.Z' floor, got {engines!r}"
    assert int(match.group(1)) == _nvmrc_major()
