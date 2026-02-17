"""Shared fixtures for inserter tests.

Provides a module-scoped template database with pre-initialized schema,
avoiding repeated GarminDBWriter DDL execution (~50ms per test → ~0.6ms per test).
"""

import shutil
from pathlib import Path

import pytest

from garmin_mcp.database.db_writer import GarminDBWriter


@pytest.fixture(scope="module")
def _schema_template_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB template with schema pre-initialized.

    Creates the database once per module and reuses the file via copy.
    """
    tmp_path: Path = tmp_path_factory.mktemp("db_template")
    db_path = tmp_path / "template.duckdb"
    GarminDBWriter(db_path=str(db_path))
    return db_path


@pytest.fixture
def initialized_db_path(_schema_template_path: Path, tmp_path: Path) -> Path:
    """Function-scoped DuckDB with schema pre-initialized via file copy.

    Each test gets its own copy of the template database, ensuring test isolation
    while avoiding the ~50ms DDL overhead per test.
    """
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(str(_schema_template_path), str(db_path))
    return db_path
