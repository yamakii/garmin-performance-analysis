"""Tests for MetadataReader.

Covers query_activity_by_date and get_activity_date.
Validates str type return (not datetime.date leakage).
"""

import datetime
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.metadata import MetadataReader

ACTIVITY_ID = 99990001
ACTIVITY_DATE = "2025-06-15"


@pytest.fixture
def metadata_reader(reader_db_path: Path) -> MetadataReader:
    """MetadataReader with a single test activity."""
    conn = duckdb.connect(str(reader_db_path))
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date) VALUES (?, ?)",
        [ACTIVITY_ID, ACTIVITY_DATE],
    )
    conn.close()
    return MetadataReader(db_path=str(reader_db_path))


@pytest.mark.unit
class TestQueryActivityByDate:
    """Tests for MetadataReader.query_activity_by_date()."""

    def test_known_date_returns_id(self, metadata_reader: MetadataReader):
        result = metadata_reader.query_activity_by_date(ACTIVITY_DATE)
        assert result == ACTIVITY_ID

    def test_unknown_date_returns_none(self, metadata_reader: MetadataReader):
        result = metadata_reader.query_activity_by_date("2099-12-31")
        assert result is None

    def test_return_type_is_int(self, metadata_reader: MetadataReader):
        result = metadata_reader.query_activity_by_date(ACTIVITY_DATE)
        assert isinstance(result, int)


@pytest.mark.unit
class TestGetActivityDate:
    """Tests for MetadataReader.get_activity_date()."""

    def test_known_id_returns_date_str(self, metadata_reader: MetadataReader):
        result = metadata_reader.get_activity_date(ACTIVITY_ID)
        assert result == ACTIVITY_DATE

    def test_return_type_is_str_not_date(self, metadata_reader: MetadataReader):
        """Critical: DuckDB returns datetime.date — reader must stringify."""
        result = metadata_reader.get_activity_date(ACTIVITY_ID)
        assert isinstance(result, str)
        assert not isinstance(result, datetime.date)

    def test_unknown_id_returns_none(self, metadata_reader: MetadataReader):
        result = metadata_reader.get_activity_date(0)
        assert result is None
