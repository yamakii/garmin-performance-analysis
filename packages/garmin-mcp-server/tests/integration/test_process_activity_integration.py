"""
Integration tests for GarminIngestWorker.process_activity()

Tests the complete workflow: data collection → performance.json → DuckDB insertion
"""

import tempfile
from pathlib import Path

import duckdb
import pytest


class TestProcessActivityIntegration:
    """Integration tests for process_activity() with DuckDB schema"""

    @pytest.mark.integration
    def test_db_schema_supports_inserters(self):
        """Test that db_writer creates tables compatible with all inserters"""
        # This test verifies that _ensure_tables() creates the correct schema
        # so that individual inserters can insert data without FK errors

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"

            # Import here to avoid circular dependency
            from garmin_mcp.database.db_writer import GarminDBWriter

            # Create database with new schema
            writer = GarminDBWriter(db_path=str(db_path))
            writer._ensure_tables()

            # Verify all normalized tables exist
            conn = duckdb.connect(str(db_path))
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            expected_tables = [
                "activities",
                "splits",
                "form_efficiency",
                "heart_rate_zones",
                "hr_efficiency",
                "performance_trends",
                "vo2_max",
                "lactate_threshold",
                "section_analyses",
            ]

            for table in expected_tables:
                assert table in table_names, f"{table} should exist"

            # Verify performance_data does NOT exist
            assert "performance_data" not in table_names

            # Test that we can insert into activities table
            conn.execute("""
                INSERT INTO activities (activity_id, activity_date, activity_name)
                VALUES (123456, '2025-01-15', 'Test Run')
                """)

            # Test that we can insert into normalized tables with FK
            conn.execute("""
                INSERT INTO splits (activity_id, split_index, distance)
                VALUES (123456, 1, 1.0)
                """)

            conn.execute("""
                INSERT INTO form_efficiency (activity_id, gct_average)
                VALUES (123456, 240.0)
                """)

            conn.execute("""
                INSERT INTO heart_rate_zones (activity_id, zone_number, zone_low_boundary)
                VALUES (123456, 1, 100)
                """)

            # Test NO FK constraint (2025-11-01 change) - orphaned records should succeed
            conn.execute("""
                INSERT INTO splits (activity_id, split_index)
                VALUES (999999, 1)
                """)

            # Verify orphaned record was inserted (no FK constraint)
            orphaned_count = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 999999"
            ).fetchone()[
                0
            ]  # type: ignore
            assert (
                orphaned_count == 1
            ), "Orphaned records should be allowed (no FK constraint)"

            conn.close()
