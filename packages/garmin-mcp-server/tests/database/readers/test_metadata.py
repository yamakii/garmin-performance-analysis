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


@pytest.fixture
def bulk_metadata_reader(reader_db_path: Path) -> MetadataReader:
    """MetadataReader seeded with three activities for bulk-query tests."""
    conn = duckdb.connect(str(reader_db_path))
    rows = [
        (1001, "2025-01-01", 5.0, 12.0),
        (1002, "2025-01-15", 10.0, 22.0),
        (1003, "2025-02-01", 21.1, 18.0),
    ]
    conn.executemany(
        "INSERT INTO activities "
        "(activity_id, activity_date, total_distance_km, temp_celsius) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.close()
    return MetadataReader(db_path=str(reader_db_path))


@pytest.mark.integration
class TestGetActivityDates:
    """Tests for MetadataReader.get_activity_dates() (bulk)."""

    def test_bulk_dates_returned_as_str(self, bulk_metadata_reader: MetadataReader):
        result = bulk_metadata_reader.get_activity_dates([1001, 1002, 1003])
        assert result == {
            1001: "2025-01-01",
            1002: "2025-01-15",
            1003: "2025-02-01",
        }
        assert all(isinstance(v, str) for v in result.values())

    def test_empty_input_returns_empty(self, bulk_metadata_reader: MetadataReader):
        assert bulk_metadata_reader.get_activity_dates([]) == {}

    def test_missing_ids_omitted(self, bulk_metadata_reader: MetadataReader):
        result = bulk_metadata_reader.get_activity_dates([1001, 9999])
        assert result == {1001: "2025-01-01"}


@pytest.mark.integration
class TestGetBulkActivityFields:
    """Tests for MetadataReader.get_bulk_activity_fields() (bulk)."""

    def test_fetch_distance_and_temp(self, bulk_metadata_reader: MetadataReader):
        result = bulk_metadata_reader.get_bulk_activity_fields(
            [1001, 1002, 1003], ["total_distance_km", "temp_celsius"]
        )
        assert result[1001] == {"total_distance_km": 5.0, "temp_celsius": 12.0}
        assert result[1002] == {"total_distance_km": 10.0, "temp_celsius": 22.0}
        assert result[1003] == {"total_distance_km": 21.1, "temp_celsius": 18.0}

    def test_invalid_field_raises_value_error(
        self, bulk_metadata_reader: MetadataReader
    ):
        with pytest.raises(ValueError, match="Invalid activity field"):
            bulk_metadata_reader.get_bulk_activity_fields(
                [1001], ["total_distance_km; DROP TABLE activities"]
            )

    def test_empty_fields_returns_empty(self, bulk_metadata_reader: MetadataReader):
        assert bulk_metadata_reader.get_bulk_activity_fields([1001], []) == {}

    def test_empty_ids_returns_empty(self, bulk_metadata_reader: MetadataReader):
        assert bulk_metadata_reader.get_bulk_activity_fields([], ["temp_celsius"]) == {}
