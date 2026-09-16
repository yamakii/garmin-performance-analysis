"""
Test suite for activities inserter

Tests the insert_activities() function that populates the activities table
with metadata from raw API files (activity.json, weather.json, gear.json).
"""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.activities import insert_activities


@pytest.mark.unit
def test_insert_activities_missing_file(initialized_db_path):
    """Test that insert_activities succeeds even without raw files (creates minimal record)."""
    db_path = initialized_db_path

    conn = duckdb.connect(str(db_path))
    # Should succeed with minimal data (just activity_id and date)
    result = insert_activities(
        activity_id=12345,
        date="2025-10-09",
        conn=conn,
    )
    assert result is True

    # Verify minimal record was created
    row = conn.execute(
        "SELECT activity_id, activity_date FROM activities WHERE activity_id = 12345"
    ).fetchone()
    assert row is not None
    assert row[0] == 12345
    assert str(row[1]) == "2025-10-09"
    conn.close()


@pytest.mark.unit
def test_insert_activities_invalid_json(initialized_db_path, tmp_path):
    """Test that insert_activities fails with invalid JSON in raw files."""
    db_path = initialized_db_path
    activity_file = tmp_path / "activity.json"

    # Create invalid JSON
    activity_file.write_text("not valid json")

    conn = duckdb.connect(str(db_path))
    result = insert_activities(
        activity_id=12345,
        date="2025-10-09",
        conn=conn,
        raw_activity_file=str(activity_file),
    )
    assert result is False
    conn.close()


@pytest.mark.unit
def test_insert_activities_minimal_data(initialized_db_path):
    """Test insert_activities with minimal required fields (just activity_id and date)."""
    db_path = initialized_db_path

    conn = duckdb.connect(str(db_path))
    result = insert_activities(
        activity_id=12345,
        date="2025-10-09",
        conn=conn,
    )
    assert result is True

    # Verify data was inserted (only metadata fields populated)
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
def test_insert_activities_complete_data(initialized_db_path, tmp_path):
    """Test insert_activities with all raw data files (activity, weather, gear)."""
    db_path = initialized_db_path

    # Create raw activity.json
    raw_activity = {
        "activityName": "Morning Run",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "startTimeLocal": "2025-10-09T06:00:00.0",
            "startTimeGMT": "2025-10-08T21:00:00.0",
        },
        "locationName": "Tokyo",
    }
    raw_activity_file = tmp_path / "activity.json"
    raw_activity_file.write_text(json.dumps(raw_activity))

    # Create raw weather.json
    raw_weather = {
        "temp": 68,  # Fahrenheit
        "relativeHumidity": 65,
        "windSpeed": 5,
        "windDirectionCompassPoint": "NE",
    }
    raw_weather_file = tmp_path / "weather.json"
    raw_weather_file.write_text(json.dumps(raw_weather))

    # Create raw gear.json (single dict, not list)
    raw_gear = {
        "gearTypeName": "Shoes",
        "customMakeModel": "Nike Pegasus 40",
    }
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(db_path))
    result = insert_activities(
        activity_id=67890,
        date="2025-10-09",
        conn=conn,
        raw_activity_file=str(raw_activity_file),
        raw_weather_file=str(raw_weather_file),
        raw_gear_file=str(raw_gear_file),
    )
    assert result is True

    # Verify metadata fields populated from raw files
    row = conn.execute("""
        SELECT
            activity_id, activity_date, activity_name, location_name,
            temp_celsius, relative_humidity_percent,
            wind_speed_kmh, wind_direction,
            gear_model, gear_type,
            total_time_seconds, total_distance_km, avg_heart_rate
        FROM activities WHERE activity_id = 67890
        """).fetchone()

    assert row is not None
    assert row[0] == 67890  # activity_id
    assert str(row[1]) == "2025-10-09"  # activity_date
    assert row[2] == "Morning Run"  # activity_name
    assert row[3] == "Tokyo"  # location_name
    assert row[4] == 20.0  # temp_celsius (converted from 68F)
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


@pytest.mark.unit
def test_insert_activities_stores_gear_nickname_and_uuid(initialized_db_path, tmp_path):
    """Gear nickname and uuid are ingested alongside the model (Issue #1207).

    Garmin's newer gear form leaves customMakeModel as the base model name, so
    the generation lives in displayName and identity lives in uuid.
    """
    raw_gear = [
        {
            "uuid": "7590ed8bcce44327b9fb46278bb3686f",
            "gearTypeName": "Shoes",
            "customMakeModel": "New Balance Fresh Foam X 1080",
            "displayName": "v15",
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    assert (
        insert_activities(
            activity_id=55555,
            date="2026-09-15",
            conn=conn,
            raw_gear_file=str(raw_gear_file),
        )
        is True
    )

    row = conn.execute("""
        SELECT gear_type, gear_model, gear_nickname, gear_uuid
        FROM activities WHERE activity_id = 55555
        """).fetchone()

    assert row == (
        "Shoes",
        "New Balance Fresh Foam X 1080",
        "v15",
        "7590ed8bcce44327b9fb46278bb3686f",
    )
    conn.close()


@pytest.mark.unit
def test_insert_activities_gear_without_nickname(initialized_db_path, tmp_path):
    """Older gear entries have displayName null -- that must not break ingest."""
    raw_gear = [
        {
            "uuid": "4a204ad6e293483e910d45081ac69301",
            "gearTypeName": "Shoes",
            "customMakeModel": "new balance fresh form x 1080 v14",
            "displayName": None,
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    assert (
        insert_activities(
            activity_id=55556,
            date="2026-09-06",
            conn=conn,
            raw_gear_file=str(raw_gear_file),
        )
        is True
    )

    row = conn.execute(
        "SELECT gear_nickname, gear_uuid FROM activities WHERE activity_id = 55556"
    ).fetchone()

    assert row == (None, "4a204ad6e293483e910d45081ac69301")
    conn.close()


@pytest.mark.unit
def test_insert_activities_empty_gear_list(initialized_db_path, tmp_path):
    """An empty gear.json means no shoe was registered, not an error.

    Every run before 2021 in the real data has `[]` here.
    """
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text("[]")

    conn = duckdb.connect(str(initialized_db_path))
    assert (
        insert_activities(
            activity_id=55557,
            date="2020-06-01",
            conn=conn,
            raw_gear_file=str(raw_gear_file),
        )
        is True
    )

    row = conn.execute("""
        SELECT gear_type, gear_model, gear_nickname, gear_uuid
        FROM activities WHERE activity_id = 55557
        """).fetchone()

    assert row == (None, None, None, None)
    conn.close()
