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


def test_insert_activities_missing_file():
    """Test that insert_activities succeeds even without raw files (creates minimal record)."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
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
            "SELECT activity_id, date FROM activities WHERE activity_id = 12345"
        ).fetchone()
        assert row is not None
        assert row[0] == 12345
        assert str(row[1]) == "2025-10-09"
        conn.close()


def test_insert_activities_invalid_json():
    """Test that insert_activities fails with invalid JSON in raw files."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        activity_file = Path(tmpdir) / "activity.json"

        # Create invalid JSON
        activity_file.write_text("not valid json")

        result = insert_activities(
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=str(activity_file),
        )
        assert result is False


def test_insert_activities_minimal_data():
    """Test insert_activities with minimal required fields (just activity_id and date)."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        result = insert_activities(
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is True

        # Verify data was inserted (only metadata fields populated)
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, date, activity_name, external_temp_c FROM activities WHERE activity_id = 12345"
        ).fetchone()
        assert row is not None
        assert row[0] == 12345
        assert str(row[1]) == "2025-10-09"
        assert row[2] is None  # No activity.json provided
        assert row[3] is None  # No weather.json provided
        conn.close()


def test_insert_activities_complete_data():
    """Test insert_activities with all raw data files (activity, weather, gear)."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

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

        # Create raw gear.json
        raw_gear = [
            {
                "gearTypeName": "Shoes",
                "customMakeModel": "Nike Pegasus 40",
            }
        ]
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
                activity_id, date, activity_name, location_name,
                external_temp_c, external_temp_f, humidity,
                wind_speed_ms, wind_direction_compass,
                gear_name, gear_type,
                total_time_seconds, total_distance_km, avg_heart_rate
            FROM activities WHERE activity_id = 67890
            """
        ).fetchone()

        assert row is not None
        assert row[0] == 67890  # activity_id
        assert str(row[1]) == "2025-10-09"  # date
        assert row[2] == "Morning Run"  # activity_name
        assert row[3] == "Tokyo"  # location_name
        assert row[4] == 20.0  # external_temp_c (68F = 20C)
        assert row[5] == 68  # external_temp_f
        assert row[6] == 65  # humidity
        assert abs(row[7] - 2.2352) < 0.01  # wind_speed_ms (5 mph ≈ 2.24 m/s)
        assert row[8] == "NE"  # wind_direction_compass
        assert row[9] == "Nike Pegasus 40"  # gear_name
        assert row[10] == "Shoes"  # gear_type
        # Metrics populated by other inserters
        assert row[11] is None  # total_time_seconds
        assert row[12] is None  # total_distance_km
        assert row[13] is None  # avg_heart_rate

        conn.close()


def test_insert_activities_real_raw_files():
    """Test insert_activities with real raw data files from the repo."""
    from tools.database.inserters.activities import insert_activities

    # Use actual raw data files
    raw_activity_file = Path("data/raw/activity/20636804823/activity.json")
    raw_weather_file = Path("data/raw/activity/20636804823/weather.json")
    raw_gear_file = Path("data/raw/activity/20636804823/gear.json")

    if not raw_activity_file.exists():
        pytest.skip("Real raw data files not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        result = insert_activities(
            activity_id=20636804823,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=str(raw_activity_file),
            raw_weather_file=(
                str(raw_weather_file) if raw_weather_file.exists() else None
            ),
            raw_gear_file=str(raw_gear_file) if raw_gear_file.exists() else None,
        )
        assert result is True

        # Verify inserted metadata
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, activity_name, external_temp_c, gear_name FROM activities WHERE activity_id = 20636804823"
        ).fetchone()
        assert row is not None
        assert row[0] == 20636804823
        # Activity name and weather/gear may or may not exist depending on data
        conn.close()
