"""Tests for WorkflowPlanner date resolution functionality."""

import tempfile
from pathlib import Path

import duckdb
import pytest

from tools.planner.workflow_planner import WorkflowPlanner


@pytest.fixture
def temp_db():
    """Create a temporary DuckDB database with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        # Create database with schema
        from tools.database.db_writer import GarminDBWriter

        _ = GarminDBWriter(str(db_path))

        # Insert test activities
        conn = duckdb.connect(str(db_path))

        # Single activity on 2025-10-05
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, date, activity_name, start_time_local,
                total_distance_km, total_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                20594901208,
                "2025-10-05",
                "戸田市 - Base",
                "2025-10-05 06:00:00",
                4.33,
                1920,
            ],
        )

        # Multiple activities on 2025-10-06
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, date, activity_name, start_time_local,
                total_distance_km, total_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                20594901209,
                "2025-10-06",
                "Morning Run",
                "2025-10-06 06:00:00",
                5.0,
                1800,
            ],
        )

        conn.execute(
            """
            INSERT INTO activities (
                activity_id, date, activity_name, start_time_local,
                total_distance_km, total_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                20594901210,
                "2025-10-06",
                "Evening Run",
                "2025-10-06 18:00:00",
                3.0,
                1200,
            ],
        )

        conn.close()
        yield str(db_path)


class TestWorkflowPlannerDateResolution:
    """Test WorkflowPlanner orchestration functionality."""

    def test_execute_full_workflow_with_date(self, temp_db):
        """Test executing workflow with date (activity_id resolved internally)."""
        from unittest.mock import MagicMock, patch

        planner = WorkflowPlanner(db_path=temp_db)

        # Mock GarminIngestWorker to avoid API calls
        mock_ingest_result = {
            "activity_id": 20594901208,
            "date": "2025-10-05",
            "status": "success",
            "files": {
                "raw_file": "data/raw/20594901208_raw.json",
                "parquet_file": "data/parquet/20594901208.parquet",
                "performance_file": "data/performance/20594901208.json",
                "precheck_file": "data/precheck/20594901208.json",
            },
        }

        with (
            patch("tools.ingest.garmin_worker.GarminIngestWorker") as mock_worker_class,
            patch(
                "tools.database.inserters.performance.insert_performance_data"
            ) as mock_insert,
            patch("pathlib.Path.exists", return_value=False),
        ):
            mock_worker_instance = MagicMock()
            mock_worker_instance.process_activity_by_date.return_value = (
                mock_ingest_result
            )
            mock_worker_class.return_value = mock_worker_instance

            result = planner.execute_full_workflow(date="2025-10-05")

            assert result["activity_id"] == 20594901208
            assert result["date"] == "2025-10-05"
            assert result["validation_status"] == "passed"
            mock_worker_instance.process_activity_by_date.assert_called_once_with(
                "2025-10-05"
            )
            mock_insert.assert_called_once()
