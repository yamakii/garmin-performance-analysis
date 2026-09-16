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


@pytest.mark.unit
def test_insert_activities_stores_gear_lifecycle(initialized_db_path, tmp_path):
    """Replacement limit, status and dates are ingested (Issue #1209).

    maximumMeters is the athlete's own limit, so it is stored in km rather than
    replaced by a generic mileage rule.
    """
    raw_gear = [
        {
            "uuid": "u-v15",
            "gearTypeName": "Shoes",
            "customMakeModel": "New Balance Fresh Foam X 1080",
            "displayName": "v15",
            "maximumMeters": 650000.0,
            "gearStatusName": "active",
            "dateBegin": "2026-09-08T00:00:00.0",
            "dateEnd": None,
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    assert (
        insert_activities(
            activity_id=66661,
            date="2026-09-15",
            conn=conn,
            raw_gear_file=str(raw_gear_file),
        )
        is True
    )

    row = conn.execute("""
        SELECT gear_max_km, gear_status, gear_since_date, gear_retired_date
        FROM activities WHERE activity_id = 66661
        """).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 650.0
    assert row[1] == "active"
    assert str(row[2]) == "2026-09-08"
    assert row[3] is None


@pytest.mark.unit
def test_insert_activities_stores_gear_retirement(initialized_db_path, tmp_path):
    """A retired pair carries its end date so alerts can skip it."""
    raw_gear = [
        {
            "uuid": "u-sk",
            "gearTypeName": "Shoes",
            "customMakeModel": "skechers go run maxroad 5",
            "maximumMeters": 643737.6,
            "gearStatusName": "retired",
            "dateBegin": "2022-11-11T15:00:00.0",
            "dateEnd": "2025-12-26T12:34:24.0",
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    insert_activities(
        activity_id=66662,
        date="2025-11-17",
        conn=conn,
        raw_gear_file=str(raw_gear_file),
    )

    row = conn.execute("""
        SELECT gear_max_km, gear_status, gear_since_date, gear_retired_date
        FROM activities WHERE activity_id = 66662
        """).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 643.7
    assert row[1] == "retired"
    assert str(row[2]) == "2022-11-11"
    assert str(row[3]) == "2025-12-26"


@pytest.mark.unit
def test_insert_activities_gear_lifecycle_missing_fields(initialized_db_path, tmp_path):
    """Older gear.json files lack these keys entirely -- all four stay null."""
    raw_gear = [
        {
            "uuid": "abc123-def456",
            "gearTypeName": "Running Shoes",
            "customMakeModel": "Nike Vaporfly 3",
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    insert_activities(
        activity_id=66663,
        date="2026-09-15",
        conn=conn,
        raw_gear_file=str(raw_gear_file),
    )

    row = conn.execute("""
        SELECT gear_model, gear_max_km, gear_status,
               gear_since_date, gear_retired_date
        FROM activities WHERE activity_id = 66663
        """).fetchone()
    conn.close()

    assert row == ("Nike Vaporfly 3", None, None, None, None)


@pytest.mark.unit
def test_insert_activities_gear_zero_limit_is_unknown(initialized_db_path, tmp_path):
    """maximumMeters of 0 means 'no limit set', not a worn-out shoe."""
    raw_gear = [
        {
            "uuid": "u-zero",
            "gearTypeName": "Shoes",
            "customMakeModel": "No Limit Shoe",
            "maximumMeters": 0,
        }
    ]
    raw_gear_file = tmp_path / "gear.json"
    raw_gear_file.write_text(json.dumps(raw_gear))

    conn = duckdb.connect(str(initialized_db_path))
    insert_activities(
        activity_id=66664,
        date="2026-09-15",
        conn=conn,
        raw_gear_file=str(raw_gear_file),
    )

    row = conn.execute(
        "SELECT gear_max_km FROM activities WHERE activity_id = 66664"
    ).fetchone()
    conn.close()

    assert row == (None,)
