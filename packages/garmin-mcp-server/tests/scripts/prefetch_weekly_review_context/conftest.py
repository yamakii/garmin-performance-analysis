"""Fixtures shared by the prefetch_weekly_review_context tests (split from test_prefetch_weekly_review_context.py, #1069)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.support.schema import init_schema


@pytest.fixture(scope="module")
def _schema_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full production schema initialized."""
    tmp_path = tmp_path_factory.mktemp("prefetch_wr_template")
    db_path = tmp_path / "template.duckdb"
    init_schema(db_path)
    return Path(db_path)


@pytest.fixture
def db_path(_schema_template: Path, tmp_path: Path) -> Path:
    """Function-scoped, schema-initialized DuckDB via file copy."""
    target = tmp_path / "prefetch_wr_test.duckdb"
    shutil.copy2(str(_schema_template), str(target))
    return target
