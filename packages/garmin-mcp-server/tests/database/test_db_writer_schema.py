"""
Tests for db_writer._ensure_tables() schema correctness

Tests that _ensure_tables() creates the correct normalized tables
and removes the old performance_data table.
"""

import tempfile
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter


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
        """Test that normalized tables have NO foreign key constraints (2025-11-01 change)"""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))

            # Act
            writer._ensure_tables()

            # Assert - verify NO foreign keys exist (orphaned records should succeed)
            conn = duckdb.connect(str(db_path))

            # Verify orphaned record insertion succeeds (no FK constraints)
            tables_to_check = [
                "splits",
                "form_efficiency",
                "heart_rate_zones",
                "hr_efficiency",
                "performance_trends",
                "vo2_max",
                "lactate_threshold",
                "form_evaluations",
                "section_analyses",
            ]

            for table in tables_to_check:
                # Insert orphaned record (activity_id=999999 doesn't exist)
                # This should SUCCEED with no FK constraints
                if table == "splits":
                    conn.execute(
                        f"INSERT INTO {table} (activity_id, split_index) VALUES (999999, 1)"
                    )
                elif table == "heart_rate_zones":
                    conn.execute(
                        f"INSERT INTO {table} (activity_id, zone_number) VALUES (999999, 1)"
                    )
                elif table == "form_evaluations":
                    conn.execute(
                        f"INSERT INTO {table} (eval_id, activity_id) VALUES (1, 999999)"
                    )
                elif table == "section_analyses":
                    conn.execute(
                        f"INSERT INTO {table} (analysis_id, activity_id, activity_date, section_type) VALUES (1, 999999, '2025-01-01', 'test')"
                    )
                else:
                    conn.execute(f"INSERT INTO {table} (activity_id) VALUES (999999)")

                # Verify insertion succeeded (no FK constraint)
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE activity_id = 999999"
                ).fetchone()[
                    0
                ]  # type: ignore
                assert (
                    count == 1
                ), f"{table} should allow orphaned records (no FK constraint)"

            conn.close()

    @pytest.mark.unit
    def test_body_composition_table_exists(self):
        """Test body_composition table creation and schema."""
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

            # body_composition table should exist
            assert (
                "body_composition" in table_names
            ), "body_composition table should be created"

    @pytest.mark.unit
    def test_body_composition_schema(self):
        """Test body_composition table has correct columns and types."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = GarminDBWriter(db_path=str(db_path))
            writer._ensure_tables()

            # Act
            conn = duckdb.connect(str(db_path))
            columns = conn.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name='body_composition' ORDER BY column_name"
            ).fetchall()
            conn.close()

            # Assert
            column_names = [col[0] for col in columns]

            # Expected columns (removed 5 device-unprovided metabolic fields)
            expected_columns = [
                "bmi",
                "body_fat_percentage",
                "bone_mass_kg",
                "date",
                "hydration_percentage",
                "measurement_id",
                "measurement_source",
                "muscle_mass_kg",
                "weight_kg",
            ]

            for col in expected_columns:
                assert col in column_names, f"Column {col} missing from schema"

            # Verify date is NOT NULL
            date_col = [c for c in columns if c[0] == "date"][0]
            assert date_col[2] == "NO", "date column should be NOT NULL"
