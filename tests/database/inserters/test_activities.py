"""
Test suite for activities inserter

Tests the insert_activities() function that populates the activities table
with metadata from performance.json files.
"""

import json
import tempfile
from pathlib import Path

import duckdb
import pytest


@pytest.mark.unit
def test_insert_activities_missing_file():
    """Test that insert_activities fails when performance file doesn't exist."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        result = insert_activities(
            performance_file="nonexistent.json",
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is False


@pytest.mark.unit
def test_insert_activities_invalid_json():
    """Test that insert_activities fails with invalid JSON."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        perf_file = Path(tmpdir) / "invalid.json"

        # Create invalid JSON
        perf_file.write_text("not valid json")

        result = insert_activities(
            performance_file=str(perf_file),
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is False


@pytest.mark.unit
def test_insert_activities_minimal_data():
    """Test insert_activities with minimal required fields."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        perf_file = Path(tmpdir) / "minimal.json"

        # Create minimal performance.json
        minimal_data = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 1800,
                "avg_pace_seconds_per_km": 360.0,
                "avg_heart_rate": 140,
                "avg_cadence": 180,
            }
        }
        perf_file.write_text(json.dumps(minimal_data))

        result = insert_activities(
            performance_file=str(perf_file),
            activity_id=12345,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result is True

        # Verify data was inserted
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, date, total_distance_km FROM activities WHERE activity_id = 12345"
        ).fetchone()
        assert row is not None
        assert row[0] == 12345
        assert str(row[1]) == "2025-10-09"
        assert row[2] == 5.0
        conn.close()


@pytest.mark.unit
def test_insert_activities_complete_data():
    """Test insert_activities with all 36 columns populated."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        perf_file = Path(tmpdir) / "complete.json"

        # Create complete performance.json with all fields
        complete_data = {
            "basic_metrics": {
                "distance_km": 10.5,
                "duration_seconds": 3600,
                "avg_pace_seconds_per_km": 342.86,
                "avg_heart_rate": 150,
                "max_heart_rate": 175,
                "avg_cadence": 185,
                "avg_power": 280,
                "normalized_power": 285,
            },
            "efficiency_metrics": {
                "cadence_stability": 1.2,
                "power_efficiency": 2.1,
                "pace_variability": 8.5,
            },
            "training_effect": {
                "aerobic_te": 3.5,
                "anaerobic_te": 0.5,
            },
            "power_to_weight": {
                "watts_per_kg": 3.8,
                "weight_kg": 70.0,
                "weight_source": "garmin",
                "weight_method": "api_fetch",
                "stability_score": 0.95,
            },
            "split_metrics": [
                {
                    "split_number": 1,
                    "elevation_gain_m": 10.0,
                    "elevation_loss_m": 5.0,
                }
            ],
        }
        perf_file.write_text(json.dumps(complete_data))

        # Mock raw data for additional fields
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

        raw_weather = {
            "temp": 68,  # Fahrenheit
            "relativeHumidity": 65,
            "windSpeed": 5,
            "windDirectionCompassPoint": "NE",
        }
        raw_weather_file = Path(tmpdir) / "weather.json"
        raw_weather_file.write_text(json.dumps(raw_weather))

        raw_gear = [
            {
                "gearTypeName": "Shoes",
                "customMakeModel": "Nike Pegasus 40",
            }
        ]
        raw_gear_file = Path(tmpdir) / "gear.json"
        raw_gear_file.write_text(json.dumps(raw_gear))

        result = insert_activities(
            performance_file=str(perf_file),
            activity_id=67890,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=str(raw_activity_file),
            raw_weather_file=str(raw_weather_file),
            raw_gear_file=str(raw_gear_file),
        )
        assert result is True

        # Verify all 36 columns
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            """
            SELECT
                activity_id, date, activity_name, start_time_local, start_time_gmt,
                total_time_seconds, total_distance_km, avg_pace_seconds_per_km,
                avg_heart_rate, max_heart_rate, avg_cadence, avg_power, normalized_power,
                cadence_stability, power_efficiency, pace_variability,
                aerobic_te, anaerobic_te, training_effect_source,
                power_to_weight, weight_kg, weight_source, weight_method, stability_score,
                external_temp_c, external_temp_f, humidity, wind_speed_ms, wind_direction_compass,
                gear_name, gear_type,
                total_elevation_gain, total_elevation_loss, location_name
            FROM activities WHERE activity_id = 67890
            """
        ).fetchone()

        assert row is not None
        assert row[0] == 67890  # activity_id
        assert str(row[1]) == "2025-10-09"  # date
        assert row[2] == "Morning Run"  # activity_name
        assert row[5] == 3600  # total_time_seconds
        assert row[6] == 10.5  # total_distance_km
        assert row[8] == 150  # avg_heart_rate
        assert row[9] == 175  # max_heart_rate
        assert row[10] == 185  # avg_cadence
        assert row[11] == 280  # avg_power
        assert row[19] == 3.8  # power_to_weight
        assert row[20] == 70.0  # weight_kg
        assert row[24] == 20.0  # external_temp_c (68F = 20C)
        assert row[25] == 68  # external_temp_f
        assert row[26] == 65  # humidity
        assert row[29] == "Nike Pegasus 40"  # gear_name
        assert row[30] == "Shoes"  # gear_type
        assert row[31] == 10.0  # total_elevation_gain
        assert row[32] == 5.0  # total_elevation_loss
        assert row[33] == "Tokyo"  # location_name

        conn.close()


@pytest.mark.unit
def test_insert_activities_upsert_behavior():
    """Test that re-inserting the same activity_id updates the row."""
    from tools.database.inserters.activities import insert_activities

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        perf_file = Path(tmpdir) / "activity.json"

        # First insertion
        data_v1 = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 1800,
                "avg_pace_seconds_per_km": 360.0,
            }
        }
        perf_file.write_text(json.dumps(data_v1))

        result1 = insert_activities(
            performance_file=str(perf_file),
            activity_id=99999,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result1 is True

        # Second insertion with updated distance
        data_v2 = {
            "basic_metrics": {
                "distance_km": 6.0,
                "duration_seconds": 2000,
                "avg_pace_seconds_per_km": 333.33,
            }
        }
        perf_file.write_text(json.dumps(data_v2))

        result2 = insert_activities(
            performance_file=str(perf_file),
            activity_id=99999,
            date="2025-10-09",
            db_path=str(db_path),
        )
        assert result2 is True

        # Verify only one row exists with updated data
        conn = duckdb.connect(str(db_path))
        rows = conn.execute(
            "SELECT COUNT(*), total_distance_km, total_time_seconds FROM activities WHERE activity_id = 99999 GROUP BY total_distance_km, total_time_seconds"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 1  # count
        assert rows[0][1] == 6.0  # updated distance
        assert rows[0][2] == 2000  # updated duration
        conn.close()


@pytest.mark.integration
def test_insert_activities_real_performance_file():
    """Test insert_activities with a real performance.json file from the repo."""
    from tools.database.inserters.activities import insert_activities

    # Use actual performance file
    perf_file = Path("data/performance/20636804823.json")
    if not perf_file.exists():
        pytest.skip("Real performance file not available")

    # Use actual raw data files
    raw_activity_file = Path("data/raw/activity/20636804823/activity.json")
    raw_weather_file = Path("data/raw/activity/20636804823/weather.json")
    raw_gear_file = Path("data/raw/activity/20636804823/gear.json")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"

        result = insert_activities(
            performance_file=str(perf_file),
            activity_id=20636804823,
            date="2025-10-09",
            db_path=str(db_path),
            raw_activity_file=(
                str(raw_activity_file) if raw_activity_file.exists() else None
            ),
            raw_weather_file=(
                str(raw_weather_file) if raw_weather_file.exists() else None
            ),
            raw_gear_file=str(raw_gear_file) if raw_gear_file.exists() else None,
        )
        assert result is True

        # Verify inserted data
        conn = duckdb.connect(str(db_path))
        row = conn.execute(
            "SELECT activity_id, total_distance_km, avg_heart_rate FROM activities WHERE activity_id = 20636804823"
        ).fetchone()
        assert row is not None
        assert row[0] == 20636804823
        assert row[1] > 0  # has distance
        assert row[2] > 0  # has heart rate
        conn.close()
