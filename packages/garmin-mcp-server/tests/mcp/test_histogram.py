"""
Tests for histogram() function - distribution analysis.
"""

import json

import duckdb
import pytest

from garmin_mcp.database.readers.aggregate import AggregateReader


@pytest.fixture
def test_db(tmp_path):
    """Create a test DuckDB database with sample data."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create splits table with sample data for histogram
    conn.execute("""
        CREATE TABLE splits (
            activity_id INTEGER,
            date DATE,
            split_number INTEGER,
            pace DOUBLE,
            heart_rate INTEGER,
            cadence INTEGER
        )
    """)

    # Insert sample data with varied pace values for histogram
    pace_values = [240, 245, 250, 255, 260, 265, 270, 275, 280, 285, 290, 295, 300]
    for i, pace in enumerate(pace_values * 5):  # 65 total rows
        conn.execute(f"""
            INSERT INTO splits VALUES
            (1, '2025-01-15', {i+1}, {pace}, 150, 180)
        """)

    # Add some NULL values
    conn.execute("""
        INSERT INTO splits VALUES
        (1, '2025-01-15', 100, NULL, 150, 180)
    """)

    conn.close()
    return db_path


@pytest.mark.integration
class TestHistogramColumn:
    """Test histogram_column method."""

    def test_histogram_pace_20_bins(self, test_db):
        """Test histogram with default 20 bins."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.histogram_column("splits", "pace", bins=20)

        # Check basic structure
        assert "column" in result
        assert result["column"] == "pace"
        assert "bins" in result
        assert "total_count" in result
        assert "statistics" in result

        # Check bins structure
        assert len(result["bins"]) <= 20
        for bin_data in result["bins"]:
            assert "min" in bin_data
            assert "max" in bin_data
            assert "count" in bin_data

        # Check statistics
        stats = result["statistics"]
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats
        assert "median" in stats

    def test_histogram_custom_bins(self, test_db):
        """Test histogram with custom bin count."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.histogram_column("splits", "pace", bins=10)

        # Should have approximately 10 bins (may be 11 due to boundary conditions)
        assert len(result["bins"]) <= 11

    def test_histogram_with_date_range(self, test_db):
        """Test histogram with date_range filter."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.histogram_column(
            "splits", "pace", bins=10, date_range=("2025-01-01", "2025-12-31")
        )

        # Should have data
        assert result["total_count"] > 0

    def test_histogram_query(self, test_db):
        """Test histogram on SQL query."""
        reader = AggregateReader(db_path=str(test_db))
        query = "SELECT pace FROM splits WHERE pace > 250"
        result = reader.histogram_column(query, "pace", bins=10)

        # Should have data
        assert result["total_count"] > 0
        assert result["statistics"]["min"] > 250

    def test_histogram_empty_result(self, test_db):
        """Test histogram on empty result."""
        reader = AggregateReader(db_path=str(test_db))
        query = "SELECT pace FROM splits WHERE 1=0"
        result = reader.histogram_column(query, "pace")

        assert result["total_count"] == 0
        assert result["bins"] == []

    def test_histogram_column_with_nulls(self, test_db):
        """Test histogram with NULL values (should be excluded)."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.histogram_column("splits", "pace", bins=10)

        # Total count should exclude NULLs
        assert result["total_count"] == 65  # 66 rows - 1 NULL

    def test_histogram_single_value(self, test_db):
        """Test histogram with single unique value."""
        reader = AggregateReader(db_path=str(test_db))
        query = "SELECT pace FROM splits WHERE pace = 250"
        result = reader.histogram_column(query, "pace", bins=10)

        # Should have 1 bin
        assert len(result["bins"]) == 1
        assert result["statistics"]["min"] == result["statistics"]["max"]

    def test_histogram_output_size_limit(self, test_db):
        """Test that histogram output is limited to ~1KB."""
        reader = AggregateReader(db_path=str(test_db))
        result = reader.histogram_column("splits", "pace", bins=20)

        # Convert to JSON and check size
        json_str = json.dumps(result)
        size_bytes = len(json_str.encode("utf-8"))

        # Should be under 2KB (generous limit, target is 1KB)
        assert size_bytes < 2048, f"Histogram output too large: {size_bytes} bytes"
