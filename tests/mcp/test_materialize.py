"""
Tests for materialize() function - query result caching with temporary views.
"""

from unittest.mock import patch

import duckdb
import pytest

from tools.mcp_server.view_manager import ViewManager, get_view_manager


@pytest.fixture
def test_db(tmp_path):
    """Create a test DuckDB database with sample data."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create splits table with sample data
    conn.execute("""
        CREATE TABLE splits (
            activity_id INTEGER,
            date DATE,
            split_number INTEGER,
            pace DOUBLE,
            heart_rate INTEGER
        )
    """)

    # Insert sample data
    for i in range(100):
        conn.execute(f"""
            INSERT INTO splits VALUES
            ({i % 3 + 1}, '2025-01-15', {i+1}, {270.0 + i % 30}, {145 + i % 20})
        """)

    conn.close()
    return db_path


@pytest.mark.integration
class TestViewManager:
    """Test ViewManager class for temporary view management."""

    def test_create_view(self, test_db):
        """Test creating a temporary view."""
        manager = ViewManager(db_path=str(test_db))
        query = "SELECT * FROM splits WHERE pace > 275"

        result = manager.create_view(query, ttl_seconds=3600)

        # Check result structure
        assert "view" in result
        assert "rows" in result
        assert "expires_at" in result

        # Check view name format
        assert result["view"].startswith("temp_view_")

        # Check row count is positive
        assert result["rows"] > 0

        # Cleanup
        manager.cleanup_view(result["view"])

    def test_view_can_be_queried(self, test_db):
        """Test that created view can be queried."""
        manager = ViewManager(db_path=str(test_db))
        query = "SELECT pace, heart_rate FROM splits WHERE pace > 280"

        result = manager.create_view(query, ttl_seconds=3600)
        view_name = result["view"]

        # Query the view
        conn = duckdb.connect(str(test_db))
        view_result = conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()
        conn.close()

        # Should have same row count
        assert view_result is not None
        assert view_result[0] == result["rows"]

        # Cleanup
        manager.cleanup_view(view_name)

    def test_view_name_uniqueness(self, test_db):
        """Test that view names are unique."""
        manager = ViewManager(db_path=str(test_db))
        query = "SELECT * FROM splits"

        result1 = manager.create_view(query)
        result2 = manager.create_view(query)

        # View names should be different
        assert result1["view"] != result2["view"]

        # Cleanup
        manager.cleanup_view(result1["view"])
        manager.cleanup_view(result2["view"])

    def test_ttl_expiration(self, test_db):
        """Test TTL-based view expiration."""
        with patch("time.time") as mock_time:
            # Start time at 1000.0
            mock_time.return_value = 1000.0

            manager = ViewManager(db_path=str(test_db))
            query = "SELECT * FROM splits"

            # Create view with 1 second TTL
            result = manager.create_view(query, ttl_seconds=1)
            view_name = result["view"]

            # View should exist immediately
            assert manager.view_exists(view_name)

            # Advance time past TTL expiration (1.5 seconds later)
            mock_time.return_value = 1001.5

            # Cleanup expired views
            manager.cleanup_expired_views()

            # View should no longer exist
            assert not manager.view_exists(view_name)

    def test_max_views_limit(self, test_db):
        """Test maximum views limit enforcement."""
        manager = ViewManager(db_path=str(test_db), max_views=5)
        query = "SELECT * FROM splits"

        # Create 6 views (exceeds limit of 5)
        view_names = []
        for _ in range(6):
            result = manager.create_view(query, ttl_seconds=3600)
            view_names.append(result["view"])

        # Only 5 views should exist (oldest one should be cleaned up)
        existing_views = [vn for vn in view_names if manager.view_exists(vn)]
        assert len(existing_views) == 5

        # First view should have been removed
        assert not manager.view_exists(view_names[0])

        # Cleanup remaining views
        for view_name in view_names[1:]:
            if manager.view_exists(view_name):
                manager.cleanup_view(view_name)

    def test_cleanup_oldest_views(self, test_db):
        """Test that oldest views are cleaned up first."""
        with patch("time.time") as mock_time:
            # Start time at 1000.0
            current_time = 1000.0
            mock_time.return_value = current_time

            manager = ViewManager(db_path=str(test_db), max_views=3)
            query = "SELECT * FROM splits"

            # Create 4 views with incrementing timestamps
            view_names = []
            for _ in range(4):
                result = manager.create_view(query, ttl_seconds=3600)
                view_names.append(result["view"])
                # Advance time by 0.1 seconds for next view
                current_time += 0.1
                mock_time.return_value = current_time

            # First view should be removed, others should exist
            assert not manager.view_exists(view_names[0])
            for view_name in view_names[1:]:
                assert manager.view_exists(view_name)

            # Cleanup
            for view_name in view_names[1:]:
                if manager.view_exists(view_name):
                    manager.cleanup_view(view_name)

    def test_manual_cleanup(self, test_db):
        """Test manual view cleanup."""
        manager = ViewManager(db_path=str(test_db))
        query = "SELECT * FROM splits"

        result = manager.create_view(query)
        view_name = result["view"]

        # View should exist
        assert manager.view_exists(view_name)

        # Manual cleanup
        manager.cleanup_view(view_name)

        # View should no longer exist
        assert not manager.view_exists(view_name)

    def test_get_view_manager_singleton(self):
        """Test get_view_manager returns singleton instance."""
        manager1 = get_view_manager()
        manager2 = get_view_manager()

        # Should be the same instance
        assert manager1 is manager2


@pytest.mark.integration
class TestViewManagerIntegration:
    """Integration tests for view manager with real queries."""

    def test_complex_query_materialization(self, test_db):
        """Test materializing complex query for performance improvement."""
        manager = ViewManager(db_path=str(test_db))

        # Complex query with aggregation
        query = """
            SELECT
                activity_id,
                AVG(pace) as avg_pace,
                AVG(heart_rate) as avg_hr,
                COUNT(*) as split_count
            FROM splits
            GROUP BY activity_id
        """

        result = manager.create_view(query)
        view_name = result["view"]

        # Query the materialized view
        conn = duckdb.connect(str(test_db))
        view_data = conn.execute(f"SELECT * FROM {view_name}").fetchall()
        conn.close()

        # Should have 3 activities
        assert len(view_data) == 3

        # Cleanup
        manager.cleanup_view(view_name)

    def test_view_reuse_for_multiple_queries(self, test_db):
        """Test that materialized view can be queried multiple times."""
        manager = ViewManager(db_path=str(test_db))
        query = "SELECT * FROM splits WHERE pace > 280"

        result = manager.create_view(query)
        view_name = result["view"]

        conn = duckdb.connect(str(test_db))

        # Multiple queries on same view
        count_result = conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()
        avg_result = conn.execute(f"SELECT AVG(pace) FROM {view_name}").fetchone()
        max_result = conn.execute(f"SELECT MAX(heart_rate) FROM {view_name}").fetchone()

        conn.close()

        # All queries should succeed
        assert count_result is not None
        assert avg_result is not None
        assert max_result is not None
        count1 = count_result[0]
        avg_pace = avg_result[0]
        max_hr = max_result[0]
        assert count1 > 0
        assert avg_pace > 280
        assert max_hr > 0

        # Cleanup
        manager.cleanup_view(view_name)
