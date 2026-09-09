"""Guards for the test-tree layout (#1068).

``tests/`` mirrors ``src/garmin_mcp/``: one directory per src package, every
directory a package, file names describe the subject. The unit / integration
distinction is carried by markers, never by directories, and file names never
carry a project phase.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {"__pycache__", "fixtures", "snapshots"}


def _test_files() -> list[Path]:
    return sorted(
        p
        for p in _TESTS.rglob("test_*.py")
        if not any(part in _SKIP_DIRS for part in p.relative_to(_TESTS).parts)
    )


@pytest.mark.unit
def test_no_layer_directories() -> None:
    """The layer split lives in markers; the directories were dissolved."""
    for name in ("unit", "integration"):
        assert not (_TESTS / name).exists(), f"tests/{name}/ must not come back"


@pytest.mark.unit
def test_every_test_directory_is_a_package() -> None:
    """A repeated basename in two non-package dirs collides under pytest's
    prepend import mode, so every directory holding tests is a package."""
    missing = sorted(
        {
            str(p.parent.relative_to(_TESTS))
            for p in _test_files()
            if not (p.parent / "__init__.py").exists()
        }
    )
    assert not missing, f"test directories without __init__.py: {missing}"


@pytest.mark.unit
def test_no_phase_named_test_files() -> None:
    """File names describe the subject, not the project phase they were born in."""
    offenders = [
        str(p.relative_to(_TESTS))
        for p in _test_files()
        if re.search(r"phase\d", p.name)
    ]
    assert not offenders, f"phase-named test files: {offenders}"


@pytest.mark.unit
def test_test_basenames_unique_within_package() -> None:
    """Under a directory that already names the layer (migrations/, readers/),
    ``foo`` and ``foo_migration`` / ``foo_integration`` must not coexist."""
    by_dir: dict[Path, set[str]] = defaultdict(set)
    for p in _test_files():
        by_dir[p.parent].add(p.stem)
    clashes = []
    for directory, stems in by_dir.items():
        for stem in stems:
            for suffix in ("_migration", "_integration"):
                if stem.endswith(suffix) and stem[: -len(suffix)] in stems:
                    clashes.append(str((directory / stem).relative_to(_TESTS)))
    assert not clashes, f"suffix-only duplicates: {clashes}"
