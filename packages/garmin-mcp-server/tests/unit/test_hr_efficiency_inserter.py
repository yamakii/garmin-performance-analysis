"""
Unit tests for hr_efficiency inserter with zone percentage support.

Tests the insert_hr_efficiency() function's ability to insert zone percentages.
"""

import json
import tempfile
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.hr_efficiency import insert_hr_efficiency


@pytest.mark.unit
class TestHREfficiencyInserter:
    """Test HR efficiency inserter with zone percentage support."""

    def test_insert_hr_efficiency_with_zone_percentages(self):
        """Test that zone percentages are correctly inserted into DuckDB."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create raw hr_zones.json with zone data
            hr_zones_data = [
                {"zoneNumber": 1, "zoneLowBoundary": 100, "secsInZone": 450.0},
                {"zoneNumber": 2, "zoneLowBoundary": 120, "secsInZone": 900.0},
                {"zoneNumber": 3, "zoneLowBoundary": 140, "secsInZone": 1200.0},
                {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 375.0},
                {"zoneNumber": 5, "zoneLowBoundary": 180, "secsInZone": 75.0},
            ]

            hr_zones_file = Path(tmpdir) / "hr_zones.json"
            with open(hr_zones_file, "w", encoding="utf-8") as f:
                json.dump(hr_zones_data, f)

            # Create raw activity.json
            activity_data = {
                "activityId": 12345,
                "summaryDTO": {"duration": 3000.0},
            }

            activity_file = Path(tmpdir) / "activity.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 12345

            # Act
            GarminDBWriter(db_path=str(db_path))
            conn = duckdb.connect(str(db_path))
            result = insert_hr_efficiency(
                activity_id=activity_id,
                conn=conn,
                raw_hr_zones_file=str(hr_zones_file),
                raw_activity_file=str(activity_file),
            )

            # Assert
            assert result is True

            # Verify data in DuckDB
            rows = conn.execute(
                "SELECT * FROM hr_efficiency WHERE activity_id = ?", [activity_id]
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            row = rows[0]

            # Check zone percentages are inserted
            assert row[9] == 15.0  # zone1_percentage
            assert row[10] == 30.0  # zone2_percentage
            assert row[11] == 40.0  # zone3_percentage
            assert row[12] == 12.5  # zone4_percentage
            assert row[13] == 2.5  # zone5_percentage

    def test_insert_hr_efficiency_missing_zone_percentages(self):
        """Test that missing zone percentages result in NULL values."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create raw hr_zones.json with NO secsInZone data
            hr_zones_data = [
                {"zoneNumber": 1, "zoneLowBoundary": 100},
                {"zoneNumber": 2, "zoneLowBoundary": 120},
                {"zoneNumber": 3, "zoneLowBoundary": 140},
                {"zoneNumber": 4, "zoneLowBoundary": 160},
                {"zoneNumber": 5, "zoneLowBoundary": 180},
            ]

            hr_zones_file = Path(tmpdir) / "hr_zones.json"
            with open(hr_zones_file, "w", encoding="utf-8") as f:
                json.dump(hr_zones_data, f)

            # Create raw activity.json
            activity_data = {
                "activityId": 67890,
                "summaryDTO": {"duration": 3000.0},
            }

            activity_file = Path(tmpdir) / "activity.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 67890

            # Act
            GarminDBWriter(db_path=str(db_path))
            conn = duckdb.connect(str(db_path))
            result = insert_hr_efficiency(
                activity_id=activity_id,
                conn=conn,
                raw_hr_zones_file=str(hr_zones_file),
                raw_activity_file=str(activity_file),
            )

            # Assert
            assert result is True

            # Verify NULL values in DuckDB
            rows = conn.execute(
                "SELECT zone1_percentage, zone2_percentage, zone3_percentage, zone4_percentage, zone5_percentage FROM hr_efficiency WHERE activity_id = ?",
                [activity_id],
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            row = rows[0]

            # All zone percentages should be NULL
            assert row[0] is None
            assert row[1] is None
            assert row[2] is None
            assert row[3] is None
            assert row[4] is None

    def test_insert_hr_efficiency_reinsertion(self):
        """Test that re-insertion updates existing records correctly."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # First insertion - create raw files
            hr_zones_data_v1 = [
                {"zoneNumber": 1, "zoneLowBoundary": 100, "secsInZone": 300.0},
                {"zoneNumber": 2, "zoneLowBoundary": 120, "secsInZone": 600.0},
                {"zoneNumber": 3, "zoneLowBoundary": 140, "secsInZone": 1500.0},
                {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 450.0},
                {"zoneNumber": 5, "zoneLowBoundary": 180, "secsInZone": 150.0},
            ]

            hr_zones_file = Path(tmpdir) / "hr_zones.json"
            with open(hr_zones_file, "w", encoding="utf-8") as f:
                json.dump(hr_zones_data_v1, f)

            activity_data = {
                "activityId": 11111,
                "summaryDTO": {"duration": 3000.0},
            }

            activity_file = Path(tmpdir) / "activity.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 11111

            # Act - First insertion
            GarminDBWriter(db_path=str(db_path))
            conn = duckdb.connect(str(db_path))
            result1 = insert_hr_efficiency(
                activity_id=activity_id,
                conn=conn,
                raw_hr_zones_file=str(hr_zones_file),
                raw_activity_file=str(activity_file),
            )
            assert result1 is True

            # Update hr_zones.json with new zone data
            hr_zones_data_v2 = [
                {"zoneNumber": 1, "zoneLowBoundary": 100, "secsInZone": 150.0},
                {"zoneNumber": 2, "zoneLowBoundary": 120, "secsInZone": 450.0},
                {"zoneNumber": 3, "zoneLowBoundary": 140, "secsInZone": 1350.0},
                {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 750.0},
                {"zoneNumber": 5, "zoneLowBoundary": 180, "secsInZone": 300.0},
            ]

            with open(hr_zones_file, "w", encoding="utf-8") as f:
                json.dump(hr_zones_data_v2, f)

            # Act - Second insertion (re-insertion)
            result2 = insert_hr_efficiency(
                activity_id=activity_id,
                conn=conn,
                raw_hr_zones_file=str(hr_zones_file),
                raw_activity_file=str(activity_file),
            )

            # Assert
            assert result2 is True

            # Verify updated data
            rows = conn.execute(
                "SELECT zone1_percentage, zone2_percentage, zone3_percentage, zone4_percentage, zone5_percentage FROM hr_efficiency WHERE activity_id = ?",
                [activity_id],
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            row = rows[0]

            # Should have updated values (v2)
            assert row[0] == 5.0
            assert row[1] == 15.0
            assert row[2] == 45.0
            assert row[3] == 25.0
            assert row[4] == 10.0

    def test_insert_hr_efficiency_partial_zone_percentages(self):
        """Test that partial zone percentages are handled correctly."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only zones 1-3 have secsInZone data
            hr_zones_data = [
                {"zoneNumber": 1, "zoneLowBoundary": 100, "secsInZone": 1500.0},
                {"zoneNumber": 2, "zoneLowBoundary": 120, "secsInZone": 1200.0},
                {"zoneNumber": 3, "zoneLowBoundary": 140, "secsInZone": 300.0},
                {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 0.0},
                {"zoneNumber": 5, "zoneLowBoundary": 180, "secsInZone": 0.0},
            ]

            hr_zones_file = Path(tmpdir) / "hr_zones.json"
            with open(hr_zones_file, "w", encoding="utf-8") as f:
                json.dump(hr_zones_data, f)

            activity_data = {
                "activityId": 22222,
                "summaryDTO": {"duration": 3000.0},
            }

            activity_file = Path(tmpdir) / "activity.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 22222

            # Act
            GarminDBWriter(db_path=str(db_path))
            conn = duckdb.connect(str(db_path))
            result = insert_hr_efficiency(
                activity_id=activity_id,
                conn=conn,
                raw_hr_zones_file=str(hr_zones_file),
                raw_activity_file=str(activity_file),
            )

            # Assert
            assert result is True

            # Verify partial data
            rows = conn.execute(
                "SELECT zone1_percentage, zone2_percentage, zone3_percentage, zone4_percentage, zone5_percentage FROM hr_efficiency WHERE activity_id = ?",
                [activity_id],
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            row = rows[0]

            # Zones 1-3 should have values
            assert row[0] == 50.0
            assert row[1] == 40.0
            assert row[2] == 10.0
            # Zones 4-5 have 0 seconds, so percentage is 0.0 (not NULL)
            assert row[3] == 0.0
            assert row[4] == 0.0
