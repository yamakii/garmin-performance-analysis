"""Unit tests for GarminDBReader.get_split_time_ranges() method."""

import duckdb
import pytest

from tools.database.db_reader import GarminDBReader
from tools.database.db_writer import GarminDBWriter


@pytest.fixture
def db_reader(tmp_path):
    """Create temporary database with test data."""
    db_path = tmp_path / "test_splits_time_ranges.duckdb"

    # Create database with test data
    writer = GarminDBWriter(str(db_path))
    writer._ensure_tables()

    # Insert test activity with splits directly
    activity_id = 12345678901
    activity_date = "2025-10-11"

    conn = duckdb.connect(str(db_path))

    # Insert activity first (foreign key requirement)
    conn.execute(
        """
        INSERT INTO activities (activity_id, date, activity_name)
        VALUES (?, ?, ?)
        """,
        (activity_id, activity_date, "Test Run"),
    )

    # Insert splits with time ranges
    splits_data = [
        (activity_id, 1, 1.0, 387.5, 0, 387, 387.5, 160),
        (activity_id, 2, 1.0, 385.2, 387, 772, 385.2, 165),
        (activity_id, 3, 1.0, 390.8, 772, 1163, 390.8, 168),
    ]

    for split in splits_data:
        conn.execute(
            """
            INSERT INTO splits (
                activity_id, split_index, distance, duration_seconds,
                start_time_s, end_time_s, pace_seconds_per_km, heart_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            split,
        )

    conn.close()

    return GarminDBReader(str(db_path))


@pytest.mark.unit
def test_get_split_time_ranges_success(db_reader):
    """Test successful retrieval of split time ranges."""
    activity_id = 12345678901

    result = db_reader.get_split_time_ranges(activity_id)

    assert isinstance(result, list)
    assert len(result) == 3

    # Verify first split
    assert result[0]["split_index"] == 1
    assert result[0]["duration_seconds"] == 387.5
    assert result[0]["start_time_s"] == 0
    assert result[0]["end_time_s"] == 387

    # Verify second split
    assert result[1]["split_index"] == 2
    assert result[1]["duration_seconds"] == 385.2
    assert result[1]["start_time_s"] == 387
    assert result[1]["end_time_s"] == 772

    # Verify third split
    assert result[2]["split_index"] == 3
    assert result[2]["duration_seconds"] == 390.8
    assert result[2]["start_time_s"] == 772
    assert result[2]["end_time_s"] == 1163


@pytest.mark.unit
def test_get_split_time_ranges_structure(db_reader):
    """Test that returned data has correct structure."""
    activity_id = 12345678901

    result = db_reader.get_split_time_ranges(activity_id)

    for split_data in result:
        assert "split_index" in split_data
        assert "duration_seconds" in split_data
        assert "start_time_s" in split_data
        assert "end_time_s" in split_data

        # Verify types
        assert isinstance(split_data["split_index"], int)
        assert isinstance(split_data["duration_seconds"], int | float)
        assert isinstance(split_data["start_time_s"], int)
        assert isinstance(split_data["end_time_s"], int)


@pytest.mark.unit
def test_get_split_time_ranges_nonexistent_activity(db_reader):
    """Test behavior with nonexistent activity ID."""
    activity_id = 99999999999

    result = db_reader.get_split_time_ranges(activity_id)

    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.unit
def test_get_split_time_ranges_sorted_by_index(db_reader):
    """Test that results are sorted by split_index."""
    activity_id = 12345678901

    result = db_reader.get_split_time_ranges(activity_id)

    # Verify ascending order
    indices = [split["split_index"] for split in result]
    assert indices == sorted(indices)
    assert indices == [1, 2, 3]
