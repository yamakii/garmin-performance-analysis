"""Database test fixtures.

Shared fixtures for database reader and inserter tests.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest


@pytest.fixture
def db_connection(temp_db_path: Path):
    """Create a DuckDB connection to a temporary database.

    Yields:
        Tuple of (connection, db_path_str) for test use.
        Connection is automatically closed after test.
    """
    conn = duckdb.connect(str(temp_db_path))
    try:
        yield conn, str(temp_db_path)
    finally:
        conn.close()


@pytest.fixture
def sample_splits_data() -> dict[str, Any]:
    """Standard splits data with 10 laps for testing.

    Contains realistic values for pace, HR, form metrics, and elevation.
    Activity ID: 20615445009.
    """
    return {
        "activityId": 20615445009,
        "lapDTOs": [
            {
                "lapIndex": i,
                "distance": 1000.0,
                "duration": 300 + i * 10,
                "averageHR": 150 + i * 2,
                "averageRunCadence": 170,
                "groundContactTime": 240 + i * 2,
                "verticalOscillation": 7.0 + i * 0.2,
                "verticalRatio": 8.0 + i * 0.1,
                "elevationGain": 5 + i,
                "elevationLoss": 2 + i * 0.5,
            }
            for i in range(1, 11)
        ],
    }


@pytest.fixture
def sample_hr_zones_data() -> list[dict[str, Any]]:
    """Standard HR zones data for testing."""
    return [
        {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 490.546},
        {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 1041.858},
        {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 507.274},
        {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 675.8},
        {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
    ]


@pytest.fixture
def sample_activity_data() -> dict[str, Any]:
    """Standard activity summary data for testing."""
    return {
        "summaryDTO": {
            "averageHR": 148.0,
            "maxHR": 175.0,
            "minHR": 120.0,
            "trainingEffectLabel": "THRESHOLD_WORK",
        }
    }


@pytest.fixture
def db_with_splits(temp_db_path: Path, sample_splits_data: dict, write_json_file):
    """Create a DuckDB database with pre-populated splits data.

    Returns:
        Tuple of (db_path_str, activity_id).
    """
    from garmin_mcp.database.db_writer import GarminDBWriter
    from garmin_mcp.database.inserters.splits import insert_splits

    splits_file = write_json_file("splits.json", sample_splits_data)
    activity_id = sample_splits_data["activityId"]

    GarminDBWriter(db_path=str(temp_db_path))
    conn = duckdb.connect(str(temp_db_path))
    insert_splits(
        activity_id=activity_id,
        conn=conn,
        raw_splits_file=str(splits_file),
    )
    conn.close()

    return str(temp_db_path), activity_id


@pytest.fixture
def db_reader_with_splits(db_with_splits):
    """Create a GarminDBReader with pre-populated splits data.

    Returns:
        Tuple of (reader, activity_id).
    """
    from garmin_mcp.database.db_reader import GarminDBReader

    db_path, activity_id = db_with_splits
    return GarminDBReader(db_path=db_path), activity_id
