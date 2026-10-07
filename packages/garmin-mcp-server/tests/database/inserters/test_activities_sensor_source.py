"""Tests for the per-run sensor source columns on activities (Issue #1459)."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.activities import (
    classify_sensors,
    insert_activities,
)

RD_POD = {
    "manufacturer": "GARMIN",
    "fitProductNumber": 2593,
    "sourceType": "ANTPLUS",
    "antplusDeviceType": "RUN",
    "bodyLocation": "WAIST_MID_BACK",
}
HRM_200 = {
    "manufacturer": "GARMIN",
    "fitProductNumber": 4606,
    "sourceType": "BLUETOOTH_LOW_ENERGY",
    "bleDeviceType": "HEART_RATE",
}


@pytest.mark.unit
def test_classify_sensors_rd_pod():
    assert classify_sensors([RD_POD]) == ("pod", "wrist")


@pytest.mark.unit
def test_classify_sensors_ble_strap():
    assert classify_sensors([HRM_200]) == ("wrist", "chest_strap")


@pytest.mark.unit
def test_classify_sensors_pod_and_strap():
    assert classify_sensors([RD_POD, HRM_200]) == ("pod", "chest_strap")


@pytest.mark.unit
def test_classify_sensors_none_or_empty():
    assert classify_sensors(None) == ("wrist", "wrist")
    assert classify_sensors([]) == ("wrist", "wrist")


@pytest.mark.integration
def test_insert_activities_writes_sensor_source(initialized_db_path, tmp_path):
    activity_file = tmp_path / "activity.json"
    activity_file.write_text(
        json.dumps(
            {
                "activityName": "Pod run",
                "activityTypeDTO": {"typeKey": "running"},
                "summaryDTO": {"startTimeLocal": "2026-10-07T20:07:00.0"},
                "metadataDTO": {"sensors": [RD_POD]},
            }
        ),
        encoding="utf-8",
    )

    conn = duckdb.connect(str(initialized_db_path))
    assert insert_activities(
        activity_id=14590001,
        date="2026-10-07",
        conn=conn,
        raw_activity_file=str(activity_file),
    )
    row = conn.execute(
        "SELECT dynamics_source, hr_source FROM activities WHERE activity_id = 14590001"
    ).fetchone()
    conn.close()

    assert row == ("pod", "wrist")


@pytest.mark.integration
def test_insert_activities_without_activity_file_leaves_sensor_null(
    initialized_db_path,
):
    conn = duckdb.connect(str(initialized_db_path))
    assert insert_activities(activity_id=14590002, date="2026-10-07", conn=conn)
    row = conn.execute(
        "SELECT dynamics_source, hr_source FROM activities WHERE activity_id = 14590002"
    ).fetchone()
    conn.close()

    assert row == (None, None)
