"""Guards for the RAM-backed test temp dir (#1078).

The sandbox mounts /tmp as tmpfs so per-test DuckDB files never queue behind
the saturated host disk, and pytest keeps only failed tests' temp dirs so that
RAM is not held after a run. Both settings are plain text here; the checks are
structural, like the CI workflow guards.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUN_SH = _REPO_ROOT / "docker" / "run.sh"
_PYPROJECT = _REPO_ROOT / "packages" / "garmin-mcp-server" / "pyproject.toml"


@pytest.mark.unit
def test_run_sh_mounts_tmp_as_tmpfs() -> None:
    """docker/run.sh passes `--tmpfs /tmp:...` with a size cap and world-writable mode."""
    text = _RUN_SH.read_text(encoding="utf-8")
    match = re.search(r"--tmpfs\s+/tmp:(\S+)", text)
    assert match, "docker/run.sh must mount /tmp as tmpfs (#1078)"
    options = match.group(1).split(",")
    assert any(o.startswith("size=") for o in options), options
    assert "mode=1777" in options, options


@pytest.mark.unit
def test_pytest_keeps_only_failed_temp_dirs() -> None:
    """pyproject keeps just the last run's failed-test temp dirs (RAM-backed /tmp)."""
    with _PYPROJECT.open("rb") as fh:
        ini = tomllib.load(fh)["tool"]["pytest"]["ini_options"]
    assert ini["tmp_path_retention_count"] == 1
    assert ini["tmp_path_retention_policy"] == "failed"
