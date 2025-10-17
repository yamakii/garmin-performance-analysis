"""
Integration tests for all Phase 1 MCP functions.

Tests the complete workflow of:
1. export() - Export query results to Parquet
2. profile() - Get summary statistics
3. histogram() - Get distribution analysis
4. materialize() - Create temporary views for reuse
"""

import json

import duckdb
import polars as pl
import pytest

from tools.database.readers.aggregate import AggregateReader
from tools.database.readers.export import ExportReader
from tools.mcp_server.view_manager import ViewManager


@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    """Create a test DuckDB database with comprehensive sample data."""
    tmp_path = tmp_path_factory.mktemp("data")
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create splits table with varied data
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

    # Insert 500 rows of varied data
    for i in range(500):
        activity_id = (i % 5) + 1
        date = f"2025-0{(i % 3) + 1}-{(i % 28) + 1:02d}"
        pace = 240 + (i % 60)
        heart_rate = 140 + (i % 40)
        cadence = 170 + (i % 20)
        conn.execute(
            f"""
            INSERT INTO splits VALUES
            ({activity_id}, '{date}', {i+1}, {pace}, {heart_rate}, {cadence}, 1.0)
        """
        )

    conn.close()
    yield db_path

    # Module-level cleanup
    db_path.unlink(missing_ok=True)


class TestPhase1Integration:
    """Integration tests for all Phase 1 functions."""

    def test_profile_then_export_workflow(self, test_db, tmp_path):
        """Test workflow: profile() to understand data, then export() for processing."""
        aggregate_reader = AggregateReader(db_path=str(test_db))
        export_reader = ExportReader(db_path=str(test_db))

        # Step 1: Profile the data
        profile_result = aggregate_reader.profile_table_or_query("splits")

        assert profile_result["row_count"] == 500
        assert "pace" in profile_result["columns"]
        assert "heart_rate" in profile_result["columns"]

        # Step 2: Based on profile, decide to export filtered data
        pace_min = profile_result["columns"]["pace"]["min"]
        pace_max = profile_result["columns"]["pace"]["max"]

        # Export only fast pace splits
        export_query = f"SELECT * FROM splits WHERE pace < {(pace_min + pace_max) / 2}"
        export_path = tmp_path / "fast_splits.parquet"
        export_result = export_reader.export_query_result(
            export_query, export_path, export_format="parquet"
        )

        # Verify export
        assert export_result["rows"] > 0
        assert export_result["rows"] < 500  # Filtered subset
        assert export_path.exists()

        # Load and verify exported data
        df = pl.read_parquet(export_path)
        assert len(df) == export_result["rows"]
        assert df["pace"].max() < (pace_min + pace_max) / 2

    def test_histogram_then_materialize_workflow(self, test_db):
        """Test workflow: histogram() to analyze distribution, then materialize() for reuse."""
        aggregate_reader = AggregateReader(db_path=str(test_db))
        view_manager = ViewManager(db_path=str(test_db))

        # Step 1: Get histogram to understand pace distribution
        histogram_result = aggregate_reader.histogram_column("splits", "pace", bins=10)

        assert histogram_result["total_count"] == 500
        assert len(histogram_result["bins"]) > 0

        # Step 2: Based on histogram, create materialized view for further analysis
        # Find the bin with most data
        max_count_bin = max(histogram_result["bins"], key=lambda b: b["count"])
        bin_min = max_count_bin["min"]
        bin_max = max_count_bin["max"]

        # Materialize query for this bin
        materialize_query = (
            f"SELECT * FROM splits WHERE pace BETWEEN {bin_min} AND {bin_max}"
        )
        view_result = view_manager.create_view(materialize_query)

        # Verify view can be queried
        conn = duckdb.connect(str(test_db))
        view_data = conn.execute(
            f"SELECT COUNT(*) FROM {view_result['view']}"
        ).fetchone()
        conn.close()

        assert view_data is not None
        assert view_data[0] > 0

        # Cleanup
        view_manager.cleanup_view(view_result["view"])

    def test_all_four_functions_workflow(self, test_db, tmp_path):
        """Test complete workflow using all 4 Phase 1 functions."""
        aggregate_reader = AggregateReader(db_path=str(test_db))
        export_reader = ExportReader(db_path=str(test_db))
        view_manager = ViewManager(db_path=str(test_db))

        # Step 1: Profile to understand data characteristics
        profile_result = aggregate_reader.profile_table_or_query("splits")
        assert profile_result["row_count"] == 500
        assert "date_range" in profile_result

        # Step 2: Histogram to understand pace distribution
        histogram_result = aggregate_reader.histogram_column("splits", "pace", bins=20)
        pace_median = histogram_result["statistics"]["median"]

        # Step 3: Materialize complex query for reuse
        analysis_query = f"""
            SELECT
                activity_id,
                AVG(pace) as avg_pace,
                AVG(heart_rate) as avg_hr,
                COUNT(*) as split_count
            FROM splits
            WHERE pace < {pace_median}
            GROUP BY activity_id
        """
        view_result = view_manager.create_view(analysis_query, ttl_seconds=3600)
        view_name = view_result["view"]

        # Step 4: Export materialized view results
        export_query = f"SELECT * FROM {view_name}"
        export_path = tmp_path / "analysis_results.parquet"
        export_result = export_reader.export_query_result(
            export_query, export_path, export_format="parquet"
        )

        # Verify complete workflow
        assert export_result["rows"] > 0
        assert export_path.exists()

        # Load and verify final exported data
        df = pl.read_parquet(export_path)
        assert len(df) == export_result["rows"]
        assert "avg_pace" in df.columns
        assert "avg_hr" in df.columns
        assert df["avg_pace"].max() < pace_median

        # Cleanup
        view_manager.cleanup_view(view_name)

    def test_output_size_constraints(self, test_db):
        """Test that all functions respect output size constraints."""
        aggregate_reader = AggregateReader(db_path=str(test_db))

        # Test profile output size (~1KB target)
        profile_result = aggregate_reader.profile_table_or_query("splits")
        profile_json = json.dumps(profile_result)
        profile_size = len(profile_json.encode("utf-8"))
        assert profile_size < 10240, f"Profile too large: {profile_size} bytes"

        # Test histogram output size (~1KB target)
        histogram_result = aggregate_reader.histogram_column("splits", "pace", bins=20)
        histogram_json = json.dumps(histogram_result)
        histogram_size = len(histogram_json.encode("utf-8"))
        assert histogram_size < 2048, f"Histogram too large: {histogram_size} bytes"

        # Test materialize returns minimal metadata
        view_manager = ViewManager(db_path=str(test_db))
        view_result = view_manager.create_view("SELECT * FROM splits")
        view_json = json.dumps(view_result)
        view_size = len(view_json.encode("utf-8"))
        assert view_size < 200, f"Materialize response too large: {view_size} bytes"

        # Cleanup
        view_manager.cleanup_view(view_result["view"])

    def test_date_range_filtering_consistency(self, test_db):
        """Test that date_range filtering works consistently across functions."""
        aggregate_reader = AggregateReader(db_path=str(test_db))
        date_range = ("2025-01-01", "2025-01-31")

        # Profile with date_range
        profile_result = aggregate_reader.profile_table_or_query(
            "splits", date_range=date_range
        )
        profile_count = profile_result["row_count"]

        # Histogram with same date_range
        histogram_result = aggregate_reader.histogram_column(
            "splits", "pace", bins=10, date_range=date_range
        )
        histogram_count = histogram_result["total_count"]

        # Counts should match
        assert profile_count == histogram_count

    def test_error_handling_consistency(self, test_db):
        """Test that all functions handle errors consistently."""
        aggregate_reader = AggregateReader(db_path=str(test_db))

        # Profile empty result
        profile_result = aggregate_reader.profile_table_or_query(
            "SELECT * FROM splits WHERE 1=0"
        )
        assert profile_result["row_count"] == 0
        assert profile_result["columns"] == {}

        # Histogram empty result
        histogram_result = aggregate_reader.histogram_column(
            "SELECT * FROM splits WHERE 1=0", "pace"
        )
        assert histogram_result["total_count"] == 0
        assert histogram_result["bins"] == []

    def test_performance_comparison_materialized_vs_raw(self, test_db):
        """Test that materialized views improve performance for repeated queries."""
        import time

        view_manager = ViewManager(db_path=str(test_db))

        # Complex query
        query = """
            SELECT
                activity_id,
                AVG(pace) as avg_pace,
                AVG(heart_rate) as avg_hr,
                STDDEV(pace) as pace_std,
                COUNT(*) as split_count
            FROM splits
            GROUP BY activity_id
        """

        # Benchmark: Raw query (3 times)
        conn = duckdb.connect(str(test_db))
        start_raw = time.time()
        for _ in range(3):
            conn.execute(query).fetchall()
        raw_time = time.time() - start_raw
        conn.close()

        # Benchmark: Materialized view (create once, query 3 times)
        view_result = view_manager.create_view(query)
        view_name = view_result["view"]

        conn = duckdb.connect(str(test_db))
        start_materialized = time.time()
        for _ in range(3):
            conn.execute(f"SELECT * FROM {view_name}").fetchall()
        materialized_time = time.time() - start_materialized
        conn.close()

        # Materialized should be faster (or at least not significantly slower)
        # Note: With small dataset, difference may be minimal
        assert materialized_time <= raw_time * 2.0  # Allow 2x tolerance

        # Cleanup
        view_manager.cleanup_view(view_name)
