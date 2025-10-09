"""
Tests for db_writer._ensure_tables() schema correctness

Tests that _ensure_tables() creates the correct normalized tables
and removes the old performance_data table.
"""

import tempfile
from pathlib import Path

import duckdb
import pytest

from tools.database.db_writer import GarminDBWriter


class TestDBWriterSchema:
    """Test db_writer._ensure_tables() schema creation"""

    @pytest.mark.unit
    def test_performance_data_table_removed(self):
        """Test that performance_data table is NOT created (old design removed)"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))

            # Act
            writer._ensure_tables()

            # Assert
            conn = duckdb.connect(str(db_path))
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            conn.close()

            # performance_data should NOT exist (old JSON storage design)
            assert (
                "performance_data" not in table_names
            ), "performance_data table should be removed (old design)"

    @pytest.mark.unit
    def test_base_tables_created(self):
        """Test that base tables (activities, section_analyses) are created"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))

            # Act
            writer._ensure_tables()

            # Assert
            conn = duckdb.connect(str(db_path))
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            conn.close()

            # Base tables should exist
            assert "activities" in table_names
            assert "section_analyses" in table_names

    @pytest.mark.unit
    def test_normalized_tables_created(self):
        """Test that 7 normalized tables are created"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))

            # Act
            writer._ensure_tables()

            # Assert
            conn = duckdb.connect(str(db_path))
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            conn.close()

            # 7 normalized tables should exist
            expected_tables = [
                "splits",
                "form_efficiency",
                "heart_rate_zones",
                "hr_efficiency",
                "performance_trends",
                "vo2_max",
                "lactate_threshold",
            ]
            for table in expected_tables:
                assert table in table_names, f"{table} table should be created"

    @pytest.mark.unit
    def test_foreign_key_constraints(self):
        """Test that normalized tables have proper foreign key constraints"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))

            # Act
            writer._ensure_tables()

            # Assert - verify foreign keys exist
            conn = duckdb.connect(str(db_path))

            # Get foreign key constraints for each table
            tables_to_check = [
                "splits",
                "form_efficiency",
                "heart_rate_zones",
                "hr_efficiency",
                "performance_trends",
                "vo2_max",
                "lactate_threshold",
            ]

            for table in tables_to_check:
                # Try to insert without parent record - should fail
                with pytest.raises(Exception) as exc_info:
                    if table == "splits":
                        conn.execute(
                            f"INSERT INTO {table} (activity_id, split_index) VALUES (999999, 1)"
                        )
                    elif table == "heart_rate_zones":
                        conn.execute(
                            f"INSERT INTO {table} (activity_id, zone_number) VALUES (999999, 1)"
                        )
                    else:
                        conn.execute(
                            f"INSERT INTO {table} (activity_id) VALUES (999999)"
                        )

                # Should fail due to foreign key constraint
                assert (
                    "foreign key" in str(exc_info.value).lower()
                    or "constraint" in str(exc_info.value).lower()
                ), f"{table} should have foreign key constraint on activity_id"

            conn.close()
