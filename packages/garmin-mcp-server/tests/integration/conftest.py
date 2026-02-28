"""Integration test fixtures for verification DB."""

import shutil
from pathlib import Path

import pytest

from tests.generate_verification_db import generate_verification_db


@pytest.fixture(scope="module")
def _verification_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate verification DB once per module.

    Uses generate_verification_db() to create the DB via production code path.
    The result is cached for the module scope so tests share the same template.

    Returns:
        Path to the template verification.duckdb file.
    """
    tmp_dir = tmp_path_factory.mktemp("verification_db_template")
    db_path = tmp_dir / "verification.duckdb"
    generate_verification_db(output_path=db_path)
    return db_path


@pytest.fixture
def verification_db_path(_verification_db_template: Path, tmp_path: Path) -> Path:
    """Provide an isolated copy of the verification DB for each test.

    Copies the module-scoped template DB so each test gets a fresh,
    independent instance that can be modified without affecting other tests.

    Returns:
        Path to a per-test copy of verification.duckdb.
    """
    dest = tmp_path / "verification.duckdb"
    shutil.copy2(_verification_db_template, dest)
    return dest
