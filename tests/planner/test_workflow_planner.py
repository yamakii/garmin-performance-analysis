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
    """Test date resolution functionality in WorkflowPlanner."""

    def test_resolve_activity_id_from_duckdb_single(self, temp_db):
        """Test resolving activity ID from DuckDB with single activity."""
        planner = WorkflowPlanner(db_path=temp_db)

        activity_id = planner.resolve_activity_id("2025-10-05")

        assert activity_id == 20594901208

    def test_resolve_activity_id_multiple_activities(self, temp_db):
        """Test error when multiple activities exist for date."""
        planner = WorkflowPlanner(db_path=temp_db)

        with pytest.raises(ValueError) as exc_info:
            planner.resolve_activity_id("2025-10-06")

        assert "Multiple activities found" in str(exc_info.value)
        assert "20594901209" in str(exc_info.value) or "20594901210" in str(
            exc_info.value
        )

    def test_resolve_activity_id_not_found(self, temp_db):
        """Test error when no activity found for date."""
        planner = WorkflowPlanner(db_path=temp_db)

        with pytest.raises(ValueError) as exc_info:
            planner.resolve_activity_id("2025-01-01")

        assert "No activities found" in str(exc_info.value)

    def test_get_activities_from_duckdb_single(self, temp_db):
        """Test getting activities from DuckDB with single result."""
        planner = WorkflowPlanner(db_path=temp_db)

        activities = planner._get_activities_from_duckdb("2025-10-05")

        assert len(activities) == 1
        assert activities[0]["activity_id"] == 20594901208
        assert activities[0]["activity_name"] == "戸田市 - Base"
        assert activities[0]["distance_km"] == 4.33
        assert activities[0]["duration_seconds"] == 1920

    def test_get_activities_from_duckdb_multiple(self, temp_db):
        """Test getting multiple activities from DuckDB."""
        planner = WorkflowPlanner(db_path=temp_db)

        activities = planner._get_activities_from_duckdb("2025-10-06")

        assert len(activities) == 2
        # Should be ordered by start_time_local
        assert activities[0]["activity_id"] == 20594901209  # Morning (06:00)
        assert activities[1]["activity_id"] == 20594901210  # Evening (18:00)

    def test_get_activities_from_duckdb_not_found(self, temp_db):
        """Test getting activities when none exist."""
        planner = WorkflowPlanner(db_path=temp_db)

        activities = planner._get_activities_from_duckdb("2025-01-01")

        assert len(activities) == 0

    def test_execute_full_workflow_with_date_only(self, temp_db):
        """Test executing workflow with date only (activity_id auto-resolved)."""
        planner = WorkflowPlanner(db_path=temp_db)

        result = planner.execute_full_workflow(date="2025-10-05")

        assert result["activity_id"] == 20594901208
        assert result["date"] == "2025-10-05"
        assert result["validation_status"] == "passed"

    def test_execute_full_workflow_with_activity_id_only(self, temp_db):
        """Test executing workflow with activity_id only (date auto-resolved)."""
        planner = WorkflowPlanner(db_path=temp_db)

        result = planner.execute_full_workflow(activity_id=20594901208)

        assert result["activity_id"] == 20594901208
        assert result["date"] == "2025-10-05"
        assert result["validation_status"] == "passed"

    def test_execute_full_workflow_no_args(self, temp_db):
        """Test error when neither activity_id nor date provided."""
        planner = WorkflowPlanner(db_path=temp_db)

        with pytest.raises(ValueError) as exc_info:
            planner.execute_full_workflow()

        assert "Either activity_id or date must be provided" in str(exc_info.value)

    def test_execute_full_workflow_with_both_args(self, temp_db):
        """Test that both activity_id and date can be provided (activity_id takes priority)."""
        planner = WorkflowPlanner(db_path=temp_db)

        result = planner.execute_full_workflow(
            activity_id=20594901208, date="2025-10-05"
        )

        assert result["activity_id"] == 20594901208
        assert result["date"] == "2025-10-05"
