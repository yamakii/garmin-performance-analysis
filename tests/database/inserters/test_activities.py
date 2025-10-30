"""
Test suite for activities inserter

Tests the insert_activities() function that populates the activities table
with metadata from raw API files (activity.json, weather.json, gear.json).
"""

import json
import tempfile
from pathlib import Path

import duckdb
import pytest


@pytest.mark.unit
def test_insert_activities_missing_file():
    """Test that insert_activities succeeds even without raw files (creates minimal record)."""
    from tools.database.db_writer import GarminDBWriter
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        # Initialize database schema
        GarminDBWriter(db_path=str(db_path))

        # Should succeed with minimal data (just activity_id and date)
        result = insert_activities(
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is True

        # Verify minimal record was created
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, activity_date FROM activities WHERE activity_id = 12345"
        ).fetchone()
        assert row is not None
        assert row[0] == 12345
        assert str(row[1]) == "2025-10-09"
        conn.close()


@pytest.mark.unit
def test_insert_activities_invalid_json():
    """Test that insert_activities fails with invalid JSON in raw files."""
    from tools.database.db_writer import GarminDBWriter
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        activity_file = Path(tmpdir) / "activity.json"

        # Initialize database schema
        GarminDBWriter(db_path=str(db_path))

        # Create invalid JSON
        activity_file.write_text("not valid json")

        result = insert_activities(
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=str(activity_file),
        )
        assert result is False


@pytest.mark.unit
def test_insert_activities_minimal_data():
    """Test insert_activities with minimal required fields (just activity_id and date)."""
    from tools.database.db_writer import GarminDBWriter
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        # Initialize database schema
        GarminDBWriter(db_path=str(db_path))

        result = insert_activities(
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is True

        # Verify data was inserted (only metadata fields populated)
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, activity_date, activity_name, temp_celsius FROM activities WHERE activity_id = 12345"
        ).fetchone()
        assert row is not None
        assert row[0] == 12345
        assert str(row[1]) == "2025-10-09"
        assert row[2] is None  # No activity.json provided
        assert row[3] is None  # No weather.json provided
        conn.close()


@pytest.mark.unit
def test_insert_activities_complete_data():
    """Test insert_activities with all raw data files (activity, weather, gear)."""
    from tools.database.db_writer import GarminDBWriter
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        # Initialize database schema
        GarminDBWriter(db_path=str(db_path))

        # Create raw activity.json
        raw_activity = {
            "activityName": "Morning Run",
            "summaryDTO": {
                "startTimeLocal": "2025-10-09T06:00:00.0",
                "startTimeGMT": "2025-10-08T21:00:00.0",
            },
            "locationName": "Tokyo",
        }
        raw_activity_file = Path(tmpdir) / "activity.json"
        raw_activity_file.write_text(json.dumps(raw_activity))

        # Create raw weather.json
        raw_weather = {
            "temp": 68,  # Fahrenheit
            "relativeHumidity": 65,
            "windSpeed": 5,
            "windDirectionCompassPoint": "NE",
        }
        raw_weather_file = Path(tmpdir) / "weather.json"
        raw_weather_file.write_text(json.dumps(raw_weather))

        # Create raw gear.json (single dict, not list)
        raw_gear = {
            "gearTypeName": "Shoes",
            "customMakeModel": "Nike Pegasus 40",
        }
        raw_gear_file = Path(tmpdir) / "gear.json"
        raw_gear_file.write_text(json.dumps(raw_gear))

        result = insert_activities(
            activity_id=67890,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=str(raw_activity_file),
            raw_weather_file=str(raw_weather_file),
            raw_gear_file=str(raw_gear_file),
        )
        assert result is True

        # Verify metadata fields populated from raw files
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            """
            SELECT
                activity_id, activity_date, activity_name, location_name,
                temp_celsius, relative_humidity_percent,
                wind_speed_kmh, wind_direction,
                gear_model, gear_type,
                total_time_seconds, total_distance_km, avg_heart_rate
            FROM activities WHERE activity_id = 67890
            """
        ).fetchone()

        assert row is not None
        assert row[0] == 67890  # activity_id
        assert str(row[1]) == "2025-10-09"  # activity_date
        assert row[2] == "Morning Run"  # activity_name
        assert row[3] == "Tokyo"  # location_name
        assert row[4] == 20.0  # temp_celsius (converted from 68°F)
        assert row[5] == 65  # relative_humidity_percent
        assert row[6] == 5  # wind_speed_kmh (stored as-is from API)
        assert row[7] == "NE"  # wind_direction
        assert row[8] == "Nike Pegasus 40"  # gear_model
        assert row[9] == "Shoes"  # gear_type
        # Metrics populated by other inserters
        assert row[10] is None  # total_time_seconds
        assert row[11] is None  # total_distance_km
        assert row[12] is None  # avg_heart_rate

        conn.close()
