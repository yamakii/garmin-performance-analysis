"""Pytest configuration and fixtures for test data.

Shared fixtures for all tests. Specialized fixtures live in:
- tests/database/conftest.py (DuckDB-specific)
- tests/handlers/conftest.py (Handler mock fixtures)
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fixture_base_path() -> Path:
    """Return the base path for test fixtures.

    Returns:
        Path to tests/fixtures/data directory (matches get_data_base_dir() behavior).
    """
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture
def dummy_activity_id() -> int:
    """Return the dummy activity ID used in test fixtures.

    Returns:
        Dummy activity ID: 12345678901
    """
    return 12345678901


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Return a temporary DuckDB database path.

    Returns:
        Path to a temporary test.duckdb file.
    """
    return tmp_path / "test.duckdb"


@pytest.fixture
def write_json_file(tmp_path: Path):
    """Factory fixture to write JSON data to a temporary file.

    Usage:
        def test_something(write_json_file):
            path = write_json_file("splits.json", {"lapDTOs": [...]})
    """

    def _write(filename: str, data: Any) -> Path:
        filepath = tmp_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    return _write


@pytest.fixture
def mock_reader_factory():
    """Factory fixture to create mock GarminDBReader instances.

    Usage:
        def test_something(mock_reader_factory):
            reader = mock_reader_factory({
                "get_splits_pace_hr": {"splits": [...]},
                "get_form_efficiency_summary": {"metrics": {}},
            })
            assert reader.get_splits_pace_hr(123) == {"splits": [...]}
    """

    def _create(method_returns: dict[str, Any] | None = None) -> MagicMock:
        reader = MagicMock()
        if method_returns:
            for method_name, return_value in method_returns.items():
                getattr(reader, method_name).return_value = return_value
        return reader

    return _create
