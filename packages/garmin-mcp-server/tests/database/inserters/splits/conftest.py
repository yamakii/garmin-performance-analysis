"""Fixtures shared by the splits tests (split from test_splits.py, #1069)."""

import json

import pytest


@pytest.fixture
def sample_raw_splits_file(tmp_path):
    """Create sample raw splits.json file with all new fields."""
    raw_splits_data = {
        "activityId": 20636804823,
        "lapDTOs": [
            {
                "lapIndex": 1,
                "distance": 1000.0,
                "duration": 387.504,
                "startTimeGMT": "2025-10-09T12:50:00.0",
                "intensityType": "INTERVAL",
                "averageSpeed": 2.581,
                "averageHR": 127,
                "averageRunCadence": 183.59375,
                "averagePower": 268,
                "groundContactTime": 251.4,
                "verticalOscillation": 7.22,
                "verticalRatio": 8.78,
                "elevationGain": 2.0,
                "elevationLoss": 2.0,
                # New fields for Phase 1
                "strideLength": 91.28,
                "maxHR": 148,
                "maxRunCadence": 184.0,
                "maxPower": 413,
                "normalizedPower": 270,
                "avgGradeAdjustedSpeed": 2.55,
            },
            {
                "lapIndex": 2,
                "distance": 1000.0,
                "duration": 390.841,
                "startTimeGMT": "2025-10-09T12:56:28.0",
                "intensityType": "INTERVAL",
                "averageSpeed": 2.559,
                "averageHR": 144,
                "averageRunCadence": 187.0,
                "averagePower": 262,
                "groundContactTime": 249.3,
                "verticalOscillation": 7.07,
                "verticalRatio": 8.68,
                "elevationGain": 0.0,
                "elevationLoss": 0.0,
                # New fields for Phase 1
                "strideLength": 89.5,
                "maxHR": 152,
                "maxRunCadence": 189.0,
                "maxPower": 390,
                "normalizedPower": 265,
                "avgGradeAdjustedSpeed": 2.52,
            },
        ],
    }

    raw_splits_file = tmp_path / "splits.json"
    with open(raw_splits_file, "w", encoding="utf-8") as f:
        json.dump(raw_splits_data, f, ensure_ascii=False, indent=2)

    return raw_splits_file
