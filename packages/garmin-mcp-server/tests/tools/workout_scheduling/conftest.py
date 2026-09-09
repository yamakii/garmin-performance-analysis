"""Fixtures shared by the workout_scheduling tests (split from test_workout_scheduling.py, #1069)."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.support.schema import init_schema


@pytest.fixture(scope="module")
def _week_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped DuckDB with the full schema pre-initialized."""

    db_path = tmp_path_factory.mktemp("week_schedule_template") / "template.duckdb"
    init_schema(db_path)
    return Path(db_path)


@pytest.fixture
def week_reader(_week_db_template: Path, tmp_path: Path) -> MagicMock:
    """A stand-in GarminDBReader whose db_path points at a fresh schema copy."""
    dest = tmp_path / "week_schedule.duckdb"
    shutil.copy2(str(_week_db_template), str(dest))
    mock = MagicMock()
    mock.db_path = dest
    return mock
