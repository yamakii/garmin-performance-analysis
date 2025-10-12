"""
Unit tests for hr_efficiency inserter with zone percentage support.

Tests the insert_hr_efficiency() function's ability to insert zone percentages.
"""

import json
import tempfile
from pathlib import Path

import duckdb

from tools.database.inserters.hr_efficiency import insert_hr_efficiency


class TestHREfficiencyInserter:
    """Test HR efficiency inserter with zone percentage support."""

    def test_insert_hr_efficiency_with_zone_percentages(self):
        """Test that zone percentages are correctly inserted into DuckDB."""
        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create performance.json with zone percentages
            performance_data = {
                "hr_efficiency_analysis": {
                    "avg_heart_rate": 150.5,
                    "training_type": "tempo_run",
                    "hr_stability": "優秀",
                    "description": "適切な心拍ゾーンで実施",
                    "zone1_percentage": 15.0,
                    "zone2_percentage": 30.0,
                    "zone3_percentage": 40.0,
                    "zone4_percentage": 12.5,
                    "zone5_percentage": 2.5,
                }
            }

            performance_file = Path(tmpdir) / "performance.json"
            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 12345

            # Act
            result = insert_hr_efficiency(
                str(performance_file), activity_id, str(db_path)
            )

            # Assert
            assert result is True

            # Verify data in DuckDB
            conn = duckdb.connect(str(db_path))
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
            # Create performance.json WITHOUT zone percentages
            performance_data = {
                "hr_efficiency_analysis": {
                    "avg_heart_rate": 145.0,
                    "training_type": "aerobic_base",
                    "hr_stability": "良好",
                    "description": "適切な心拍ゾーンで実施",
                }
            }

            performance_file = Path(tmpdir) / "performance.json"
            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 67890

            # Act
            result = insert_hr_efficiency(
                str(performance_file), activity_id, str(db_path)
            )

            # Assert
            assert result is True

            # Verify NULL values in DuckDB
            conn = duckdb.connect(str(db_path))
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
            # First insertion
            performance_data_v1 = {
                "hr_efficiency_analysis": {
                    "avg_heart_rate": 150.0,
                    "training_type": "tempo_run",
                    "hr_stability": "優秀",
                    "zone1_percentage": 10.0,
                    "zone2_percentage": 20.0,
                    "zone3_percentage": 50.0,
                    "zone4_percentage": 15.0,
                    "zone5_percentage": 5.0,
                }
            }

            performance_file = Path(tmpdir) / "performance.json"
            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data_v1, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 11111

            # Act - First insertion
            result1 = insert_hr_efficiency(
                str(performance_file), activity_id, str(db_path)
            )
            assert result1 is True

            # Update performance.json with new zone percentages
            performance_data_v2 = {
                "hr_efficiency_analysis": {
                    "avg_heart_rate": 155.0,
                    "training_type": "threshold_work",
                    "hr_stability": "変動あり",
                    "zone1_percentage": 5.0,
                    "zone2_percentage": 15.0,
                    "zone3_percentage": 45.0,
                    "zone4_percentage": 25.0,
                    "zone5_percentage": 10.0,
                }
            }

            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data_v2, f)

            # Act - Second insertion (re-insertion)
            result2 = insert_hr_efficiency(
                str(performance_file), activity_id, str(db_path)
            )

            # Assert
            assert result2 is True

            # Verify updated data
            conn = duckdb.connect(str(db_path))
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
            # Only zones 1-3 have percentages
            performance_data = {
                "hr_efficiency_analysis": {
                    "avg_heart_rate": 140.0,
                    "training_type": "aerobic_base",
                    "hr_stability": "優秀",
                    "zone1_percentage": 50.0,
                    "zone2_percentage": 40.0,
                    "zone3_percentage": 10.0,
                    # zone4_percentage and zone5_percentage are missing
                }
            }

            performance_file = Path(tmpdir) / "performance.json"
            with open(performance_file, "w", encoding="utf-8") as f:
                json.dump(performance_data, f)

            db_path = Path(tmpdir) / "test.duckdb"
            activity_id = 22222

            # Act
            result = insert_hr_efficiency(
                str(performance_file), activity_id, str(db_path)
            )

            # Assert
            assert result is True

            # Verify partial data
            conn = duckdb.connect(str(db_path))
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
            # Zones 4-5 should be NULL
            assert row[3] is None
            assert row[4] is None
