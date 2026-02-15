"""Tests for migrate_time_series_to_duckdb.py script.

Tests cover:
- Dry run mode
- Single activity migration
- Multiple activity migration
- Data integrity verification
- Error handling
"""

import json

import duckdb
import pytest

from garmin_mcp.scripts.migrate_time_series_to_duckdb import (
    TimeSeriesMigrator,
)


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary DuckDB path."""
    db_path = tmp_path / "test.duckdb"
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_raw_dir(tmp_path):
    """Create temporary raw data directory with test data."""
    raw_dir = tmp_path / "raw"
    activity_dir = raw_dir / "activity"
    activity_dir.mkdir(parents=True)

    # Create test activity directories
    test_activities = [12345, 67890]

    for activity_id in test_activities:
        act_dir = activity_dir / str(activity_id)
        act_dir.mkdir()

        # Create activity.json with date
        activity_json = {
            "activityId": activity_id,
            "startTimeLocal": "2025-01-15 10:00:00",
            "beginTimestamp": "2025-01-15T10:00:00Z",
        }
        with open(act_dir / "activity.json", "w", encoding="utf-8") as f:
            json.dump(activity_json, f)

        # Create activity_details.json with minimal time series data
        activity_details = {
            "metricDescriptors": [
                {"key": "sumDuration", "metricsIndex": 0, "unit": {"factor": 1000.0}},
                {"key": "directHeartRate", "metricsIndex": 1, "unit": {"factor": 1.0}},
                {"key": "directSpeed", "metricsIndex": 2, "unit": {"factor": 0.1}},
            ],
            "activityDetailMetrics": [
                {"metrics": [1, 120, 30]},  # 1s, 120bpm, 3.0m/s
                {"metrics": [2, 125, 32]},  # 2s, 125bpm, 3.2m/s
                {"metrics": [3, 130, 35]},  # 3s, 130bpm, 3.5m/s
            ],
        }
        with open(act_dir / "activity_details.json", "w", encoding="utf-8") as f:
            json.dump(activity_details, f)

    return raw_dir


@pytest.mark.unit
def test_migrator_initialization(temp_raw_dir, temp_db_path):
    """Test TimeSeriesMigrator initialization."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    assert migrator.raw_dir == temp_raw_dir
    assert migrator.db_path == temp_db_path
    assert migrator.activity_dir == temp_raw_dir / "activity"


@pytest.mark.unit
def test_get_all_activities_from_raw(temp_raw_dir, temp_db_path):
    """Test scanning raw data directory for activities."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    activities = migrator.get_all_activities_from_raw()

    # Should find 2 test activities
    assert len(activities) == 2
    activity_ids = [aid for aid, _ in activities]
    assert 12345 in activity_ids
    assert 67890 in activity_ids


@pytest.mark.unit
def test_check_activity_details_exists(temp_raw_dir, temp_db_path):
    """Test checking if activity_details.json exists."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Existing activity
    assert migrator.check_activity_details_exists(12345) is True

    # Non-existing activity
    assert migrator.check_activity_details_exists(99999) is False


@pytest.mark.unit
def test_migration_dry_run(temp_raw_dir, temp_db_path):
    """Test dry run mode - should not insert any data."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Get activities before dry run
    activities = migrator.get_all_activities_from_raw()

    # Dry run should succeed without errors
    summary = migrator.migrate_all(dry_run=True)

    assert summary["total"] == len(activities)
    assert summary["dry_run"] is True

    # Verify no data was inserted (table exists but should be empty)
    conn = duckdb.connect(str(temp_db_path))
    row_count = conn.execute("SELECT COUNT(*) FROM time_series_metrics").fetchone()
    conn.close()

    assert row_count[0] == 0  # No rows should exist after dry run


@pytest.mark.unit
def test_migration_single_activity(temp_raw_dir, temp_db_path):
    """Test migrating a single activity."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate single activity
    result = migrator.migrate_single_activity(12345, "2025-01-15")

    assert result["status"] == "success"
    assert result["activity_id"] == 12345
    assert "data_points" in result

    # Verify data was inserted
    conn = duckdb.connect(str(temp_db_path))
    count_result = conn.execute(
        "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?", [12345]
    ).fetchone()
    conn.close()

    assert count_result is not None
    assert count_result[0] == 3  # 3 data points in test data


@pytest.mark.unit
def test_migration_all_activities(temp_raw_dir, temp_db_path):
    """Test migrating all activities."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate all
    summary = migrator.migrate_all()

    assert summary["total"] == 2
    assert summary["success"] == 2
    assert summary["skipped"] == 0
    assert summary["error"] == 0

    # Verify all data was inserted
    conn = duckdb.connect(str(temp_db_path))
    result = conn.execute("SELECT COUNT(*) FROM time_series_metrics").fetchone()
    conn.close()

    assert result is not None
    assert result[0] == 6  # 3 data points × 2 activities


@pytest.mark.unit
def test_migration_integrity(temp_raw_dir, temp_db_path):
    """Test data integrity after migration."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate all
    migrator.migrate_all()

    # Verify integrity
    integrity_result = migrator.verify_integrity()

    assert integrity_result["total_activities"] == 2
    assert integrity_result["verified"] == 2
    assert integrity_result["mismatches"] == 0
    assert len(integrity_result["errors"]) == 0


@pytest.mark.unit
def test_migration_missing_activity_details(temp_raw_dir, temp_db_path):
    """Test handling missing activity_details.json."""
    # Create activity without activity_details.json
    act_dir = temp_raw_dir / "activity" / "88888"
    act_dir.mkdir()

    activity_json = {
        "activityId": 88888,
        "startTimeLocal": "2025-01-15 10:00:00",
    }
    with open(act_dir / "activity.json", "w", encoding="utf-8") as f:
        json.dump(activity_json, f)

    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate all (should skip activity without activity_details.json)
    summary = migrator.migrate_all()

    # Should skip the activity without activity_details.json
    assert summary["total"] == 3  # Now we have 3 activities
    assert summary["success"] == 2  # Only 2 have activity_details.json
    assert summary["skipped"] == 1  # 1 skipped


@pytest.mark.unit
def test_migration_specific_activity_ids(temp_raw_dir, temp_db_path):
    """Test migrating specific activity IDs."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate only one activity
    summary = migrator.migrate_all(activity_ids=[12345])

    assert summary["total"] == 1
    assert summary["success"] == 1

    # Verify only one activity was inserted
    conn = duckdb.connect(str(temp_db_path))
    activity_ids = conn.execute(
        "SELECT DISTINCT activity_id FROM time_series_metrics"
    ).fetchall()
    conn.close()

    assert len(activity_ids) == 1
    assert activity_ids[0][0] == 12345


@pytest.mark.unit
def test_verify_integrity_with_mismatch(temp_raw_dir, temp_db_path):
    """Test integrity verification with data point count mismatch."""
    migrator = TimeSeriesMigrator(
        raw_dir=temp_raw_dir,
        db_path=temp_db_path,
    )

    # Migrate all
    migrator.migrate_all()

    # Manually delete one data point to create mismatch
    conn = duckdb.connect(str(temp_db_path))
    conn.execute(
        "DELETE FROM time_series_metrics "
        "WHERE activity_id = 12345 AND timestamp_s = 1"
    )
    conn.close()

    # Verify integrity (should detect mismatch)
    integrity_result = migrator.verify_integrity()

    assert integrity_result["mismatches"] == 1
    assert len(integrity_result["mismatch_details"]) == 1

    mismatch = integrity_result["mismatch_details"][0]
    assert mismatch["activity_id"] == 12345
    assert mismatch["expected"] == 3
    assert mismatch["actual"] == 2
