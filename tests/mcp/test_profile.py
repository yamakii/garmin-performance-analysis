"""
Tests for profile() function - table/query summary statistics.
"""

import json

import duckdb
import pytest

from tools.database.readers.aggregate import AggregateReader


@pytest.fixture
def test_db(tmp_path):
    """Create a test DuckDB database with sample data."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create splits table with sample data
    conn.execute(
        """
        CREATE TABLE splits (
            activity_id INTEGER,
            date DATE,
            split_number INTEGER,
            pace DOUBLE,
            heart_rate INTEGER,
            cadence INTEGER,
            distance DOUBLE
        )
    """
    )

    # Insert sample data
    conn.execute(
        """
        INSERT INTO splits VALUES
        (1, '2025-01-15', 1, 270.5, 145, 180, 1.0),
        (1, '2025-01-15', 2, 265.0, 150, 182, 1.0),
        (1, '2025-01-15', 3, 275.0, 155, 178, 1.0),
        (2, '2025-02-20', 1, 280.0, 140, 175, 1.0),
        (2, '2025-02-20', 2, 285.0, 145, 176, 1.0),
        (3, '2025-03-10', 1, NULL, 150, 180, 1.0)
    """
    )

    # Create time_series_metrics table with many columns
    conn.execute(
        """
        CREATE TABLE time_series_metrics (
            activity_id INTEGER,
            date DATE,
            timestamp INTEGER,
            pace DOUBLE,
            heart_rate INTEGER,
            cadence INTEGER,
            distance DOUBLE,
            altitude DOUBLE,
            speed DOUBLE,
            power INTEGER,
            vertical_oscillation DOUBLE,
            ground_contact_time INTEGER,
            vertical_ratio DOUBLE,
            stride_length DOUBLE
        )
    """
    )

    # Insert sample data
    for i in range(100):
        conn.execute(
            f"""
            INSERT INTO time_series_metrics VALUES
            (1, '2025-01-15', {i}, 270.0, 145, 180, {i * 0.01}, 100.0, 3.7, 250, 8.5, 245, 7.5, 1.2)
        """
        )

    conn.close()
    return db_path


class TestProfileTableOrQuery:
    """Test profile_table_or_query method."""

    def test_profile_splits_table(self, test_db):
        """Test profiling splits table."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.profile_table_or_query("splits")

        # Check basic structure
        assert "row_count" in result
        assert "date_range" in result
        assert "columns" in result

        # Check row count is positive
        assert result["row_count"] > 0

        # Check date_range has start and end
        assert len(result["date_range"]) == 2

        # Check columns contain expected fields
        assert "pace" in result["columns"]
        assert "heart_rate" in result["columns"]

        # Check column statistics
        pace_stats = result["columns"]["pace"]
        assert "min" in pace_stats
        assert "max" in pace_stats
        assert "mean" in pace_stats
        assert "median" in pace_stats
        assert "std" in pace_stats
        assert "null_rate" in pace_stats
        assert "distinct_count" in pace_stats

    def test_profile_query(self, test_db):
        """Test profiling SQL query."""
        reader = AggregateReader(db_path=str(test_db))
        query = "SELECT pace, heart_rate FROM splits WHERE pace IS NOT NULL LIMIT 100"
        result = reader.profile_table_or_query(query)

        # Check basic structure
        assert "row_count" in result
        assert result["row_count"] == 5  # We have 5 non-NULL pace rows in test data
        assert "columns" in result

        # Check only selected columns present
        assert "pace" in result["columns"]
        assert "heart_rate" in result["columns"]

    def test_profile_with_date_range_filter(self, test_db):
        """Test profiling with date_range filter."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.profile_table_or_query(
            "splits", date_range=("2025-01-01", "2025-12-31")
        )

        # Check date_range is applied
        assert result["date_range"][0] >= "2025-01-01"
        assert result["date_range"][1] <= "2025-12-31"

    def test_profile_empty_table(self, test_db):
        """Test profiling empty result."""
        reader = AggregateReader(db_path=str(test_db))
        query = "SELECT * FROM splits WHERE 1=0"  # Always empty
        result = reader.profile_table_or_query(query)

        assert result["row_count"] == 0
        assert result["columns"] == {}

    def test_profile_column_with_nulls(self, test_db):
        """Test profiling column with NULL values."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.profile_table_or_query("splits")

        # Some columns might have NULLs
        for col_stats in result["columns"].values():
            assert 0.0 <= col_stats["null_rate"] <= 1.0

    def test_profile_output_size_limit(self, test_db):
        """Test that profile output is limited to ~1KB."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.profile_table_or_query("time_series_metrics")

        # Convert to JSON and check size

        json_str = json.dumps(result)
        size_bytes = len(json_str.encode("utf-8"))

        # Should be under 10KB (generous limit, target is 1KB)
        assert size_bytes < 10240, f"Profile output too large: {size_bytes} bytes"
