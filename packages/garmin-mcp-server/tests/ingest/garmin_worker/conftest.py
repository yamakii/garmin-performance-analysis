"""Fixtures shared by the garmin_worker tests (split from test_garmin_worker.py, #1069)."""

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Create GarminIngestWorker instance with isolated tmp database."""

    # Prevent real Garmin API calls on cache miss
    def _no_api():
        raise ValueError("No credentials in test")

    monkeypatch.setattr(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        _no_api,
    )
    worker = GarminIngestWorker()
    # Use tmp_path for isolated database to avoid interference
    worker._db_path = tmp_path / "test_garmin.duckdb"
    return worker


@pytest.fixture
def sample_raw_data():
    """Sample raw data matching actual Garmin API response structure."""
    return {
        "activity": {
            "activityId": 20464005432,
            "activityName": "Morning Run",
            "startTimeLocal": "2025-09-22 06:30:00",
            "distance": 5000,
            "duration": 1500,
            "averageHR": 145,
        },
        "splits": {
            "activityId": 20464005432,
            "lapDTOs": [
                {
                    "startTimeGMT": "2025-09-22T06:30:00.0",
                    "distance": 1000,
                    "duration": 300.0,
                    "averageSpeed": 3.33,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "averagePower": 250,
                    "groundContactTime": 240,
                    "verticalOscillation": 7.5,
                    "verticalRatio": 8.5,
                    "elevationGain": 10,
                    "elevationLoss": 5,
                    "maxElevation": 50,
                    "minElevation": 40,
                },
                {
                    "startTimeGMT": "2025-09-22T06:35:00.0",
                    "distance": 1000,
                    "duration": 295.0,
                    "averageSpeed": 3.39,
                    "averageHR": 145,
                    "averageRunCadence": 172,
                    "averagePower": 255,
                    "groundContactTime": 238,
                    "verticalOscillation": 7.3,
                    "verticalRatio": 8.3,
                    "elevationGain": 15,
                    "elevationLoss": 8,
                    "maxElevation": 55,
                    "minElevation": 42,
                },
            ],
            "eventDTOs": [],
        },
        "weather": {
            "temp": 18,
            "apparentTemp": 16,
            "windSpeed": 5,
            "relativeHumidity": 65,
            "weatherTypeDTO": {"weatherTypePk": 1},
        },
        "gear": [
            {
                "gearPk": 12345,
                "customMakeModel": "Nike Pegasus",
                "gearTypeName": "Shoes",
                "gearStatusName": "active",
            }
        ],
        "hr_zones": [
            {"zoneNumber": 1, "secsInZone": 300.0, "zoneLowBoundary": 100},
            {"zoneNumber": 2, "secsInZone": 600.0, "zoneLowBoundary": 120},
            {"zoneNumber": 3, "secsInZone": 400.0, "zoneLowBoundary": 140},
            {"zoneNumber": 4, "secsInZone": 200.0, "zoneLowBoundary": 160},
            {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 180},
        ],
    }
