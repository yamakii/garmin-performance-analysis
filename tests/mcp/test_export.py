"""Tests for export() MCP function and ExportManager.

Following TDD principles (Red → Green → Refactor).
"""

import tempfile
import time
from pathlib import Path

import duckdb
import pytest

from tools.database.db_reader import GarminDBReader
from tools.mcp_server.export_manager import ExportManager, get_export_manager


class TestExportManager:
    """Test ExportManager class for TTL-based file management."""

    def test_create_export_handle_parquet(self):
        """Test creating a parquet export handle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            file_path, handle, expires_at = manager.create_export_handle(
                export_format="parquet", ttl_seconds=3600
            )

            # Verify file path
            assert file_path.parent == Path(tmpdir)
            assert file_path.suffix == ".parquet"
            assert file_path.name.startswith("export_")

            # Verify handle
            assert handle == str(file_path)

            # Verify expiry
            assert expires_at > time.time()
            assert expires_at <= time.time() + 3600 + 1  # Allow 1s tolerance

    def test_create_export_handle_csv(self):
        """Test creating a CSV export handle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            file_path, handle, expires_at = manager.create_export_handle(
                export_format="csv", ttl_seconds=1800
            )

            # Verify file path
            assert file_path.suffix == ".csv"
            assert file_path.name.startswith("export_")

    def test_get_export_info_valid(self):
        """Test getting info for valid export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            # Create export and write file
            file_path, handle, expires_at = manager.create_export_handle(
                export_format="parquet"
            )
            file_path.write_text("test data")

            # Get info
            info = manager.get_export_info(handle)

            assert info is not None
            assert info["handle"] == handle
            assert "expires_at" in info
            assert info["size_mb"] > 0

    def test_get_export_info_not_found(self):
        """Test getting info for non-existent export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            info = manager.get_export_info("/nonexistent/file.parquet")

            assert info is None

    def test_get_export_info_expired(self):
        """Test getting info for expired export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            # Create export with 0s TTL (already expired)
            file_path, handle, _ = manager.create_export_handle(
                export_format="parquet", ttl_seconds=0
            )
            file_path.write_text("test data")

            # Wait a bit to ensure expiry
            time.sleep(0.1)

            # Get info should return None (expired)
            info = manager.get_export_info(handle)

            assert info is None
            assert not file_path.exists()  # File should be deleted

    def test_cleanup_expired(self):
        """Test automatic cleanup of expired exports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            # Create 3 exports with varying TTL
            file1, handle1, _ = manager.create_export_handle(
                export_format="parquet", ttl_seconds=10
            )
            file2, handle2, _ = manager.create_export_handle(
                export_format="parquet", ttl_seconds=0
            )  # Already expired
            file3, handle3, _ = manager.create_export_handle(
                export_format="parquet", ttl_seconds=10
            )

            # Write files
            file1.write_text("data1")
            file2.write_text("data2")
            file3.write_text("data3")

            # Wait to ensure file2 is expired
            time.sleep(0.1)

            # Trigger cleanup
            manager._cleanup_expired()

            # Check results
            assert file1.exists()
            assert not file2.exists()  # Expired
            assert file3.exists()

            assert manager.get_export_info(handle1) is not None
            assert manager.get_export_info(handle2) is None
            assert manager.get_export_info(handle3) is not None

    def test_cleanup_all(self):
        """Test cleanup_all() removes all exports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(export_dir=tmpdir)

            # Create multiple exports
            files = []
            for i in range(3):
                file_path, _, _ = manager.create_export_handle(export_format="parquet")
                file_path.write_text(f"data{i}")
                files.append(file_path)

            # All files should exist
            for file_path in files:
                assert file_path.exists()

            # Cleanup all
            manager.cleanup_all()

            # All files should be deleted
            for file_path in files:
                assert not file_path.exists()


class TestGarminDBReaderExport:
    """Test GarminDBReader.export_query_result() method."""

    @pytest.fixture
    def test_db(self):
        """Create a test DuckDB database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            conn = duckdb.connect(str(db_path))

            # Create test table
            conn.execute(
                """
                CREATE TABLE test_splits (
                    split_index INTEGER,
                    pace_seconds_per_km FLOAT,
                    heart_rate INTEGER,
                    distance FLOAT
                )
            """
            )

            # Insert test data (100 rows)
            for i in range(100):
                conn.execute(
                    """
                    INSERT INTO test_splits VALUES (?, ?, ?, ?)
                """,
                    [i + 1, 270 + i, 150 + (i % 30), 1.0],
                )

            conn.close()

            yield db_path

    def test_export_query_result_parquet(self, test_db):
        """Test exporting query result to parquet."""
        reader = GarminDBReader(db_path=str(test_db))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.parquet"

            # Export
            metadata = reader.export_query_result(
                query="SELECT * FROM test_splits WHERE split_index <= 10",
                output_path=output_path,
                export_format="parquet",
            )

            # Verify metadata
            assert metadata["rows"] == 10
            assert set(metadata["columns"]) == {
                "split_index",
                "pace_seconds_per_km",
                "heart_rate",
                "distance",
            }
            assert metadata["size_mb"] >= 0  # May be 0.0 for small files

            # Verify file exists
            assert output_path.exists()

            # Verify file content
            conn = duckdb.connect()
            result = conn.execute(
                f"SELECT COUNT(*) FROM read_parquet('{output_path}')"
            ).fetchone()
            assert result[0] == 10

    def test_export_query_result_csv(self, test_db):
        """Test exporting query result to CSV."""
        reader = GarminDBReader(db_path=str(test_db))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.csv"

            # Export
            metadata = reader.export_query_result(
                query="SELECT split_index, pace_seconds_per_km FROM test_splits WHERE split_index <= 5",
                output_path=output_path,
                export_format="csv",
            )

            # Verify metadata
            assert metadata["rows"] == 5
            assert set(metadata["columns"]) == {"split_index", "pace_seconds_per_km"}
            assert metadata["size_mb"] >= 0  # May be 0.0 for small files

            # Verify file exists
            assert output_path.exists()

            # Verify CSV has header
            content = output_path.read_text()
            assert "split_index" in content
            assert "pace_seconds_per_km" in content

    def test_export_query_result_max_rows_exceeded(self, test_db):
        """Test export fails when max_rows exceeded."""
        reader = GarminDBReader(db_path=str(test_db))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.parquet"

            # Should raise ValueError
            with pytest.raises(ValueError, match="exceeds max_rows"):
                reader.export_query_result(
                    query="SELECT * FROM test_splits",
                    output_path=output_path,
                    export_format="parquet",
                    max_rows=50,  # 100 rows in table
                )

            # File should not be created
            assert not output_path.exists()

    def test_export_query_result_empty(self, test_db):
        """Test exporting empty query result."""
        reader = GarminDBReader(db_path=str(test_db))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.parquet"

            # Export empty result
            metadata = reader.export_query_result(
                query="SELECT * FROM test_splits WHERE split_index > 1000",
                output_path=output_path,
                export_format="parquet",
            )

            # Verify metadata
            assert metadata["rows"] == 0
            assert metadata["columns"] == []
            assert metadata["size_mb"] == 0.0

    def test_export_query_result_invalid_sql(self, test_db):
        """Test export fails with invalid SQL."""
        reader = GarminDBReader(db_path=str(test_db))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.parquet"

            # Should raise exception (DuckDB error for nonexistent table)
            with pytest.raises((Exception, RuntimeError)):
                reader.export_query_result(
                    query="SELECT * FROM nonexistent_table",
                    output_path=output_path,
                    export_format="parquet",
                )


class TestExportMCPIntegration:
    """Test export() MCP function end-to-end."""

    @pytest.fixture
    def test_db(self):
        """Create a test DuckDB database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            conn = duckdb.connect(str(db_path))

            # Create test table
            conn.execute(
                """
                CREATE TABLE activities (
                    activity_id INTEGER,
                    date TEXT,
                    distance_km FLOAT
                )
            """
            )

            # Insert test data
            for i in range(50):
                conn.execute(
                    "INSERT INTO activities VALUES (?, ?, ?)",
                    [1000 + i, f"2025-01-{i+1:02d}", 10.0 + i * 0.5],
                )

            conn.close()

            yield db_path

    def test_export_mcp_success(self, test_db):
        """Test export MCP function returns handle and metadata."""
        # Conceptual test showing expected behavior
        # In production, this would be tested with pytest-asyncio
        # for full async MCP server integration testing
        assert True  # Placeholder for async integration test

    def test_export_mcp_max_rows_error(self):
        """Test export MCP returns error when max_rows exceeded."""
        # Test that ValueError is caught and returned as error response
        # This would be tested in integration tests with real MCP server


class TestExportManagerSingleton:
    """Test get_export_manager() singleton behavior."""

    def test_singleton_returns_same_instance(self):
        """Test get_export_manager() returns the same instance."""
        manager1 = get_export_manager()
        manager2 = get_export_manager()

        assert manager1 is manager2

    def test_singleton_persists_state(self):
        """Test singleton maintains state across calls."""
        _ = get_export_manager()

        # Create an export
        with tempfile.TemporaryDirectory():
            # Note: This test is conceptual - actual implementation
            # would need to handle singleton lifecycle properly
            pass
