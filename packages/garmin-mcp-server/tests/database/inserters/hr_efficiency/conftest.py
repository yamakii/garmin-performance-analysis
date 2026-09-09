"""Fixtures shared by the hr_efficiency tests (split from test_hr_efficiency.py, #1069)."""

import json

import pytest


@pytest.fixture
def sample_raw_files(tmp_path):
    """Create sample hr_zones.json and activity.json files."""
    # Create hr_zones.json
    hr_zones_data = [
        {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 490.546},
        {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 1041.858},
        {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 507.274},
        {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 675.8},
        {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
    ]
    hr_zones_file = tmp_path / "hr_zones.json"
    with open(hr_zones_file, "w", encoding="utf-8") as f:
        json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

    # Create activity.json
    activity_data = {
        "summaryDTO": {
            "averageHR": 148.0,
            "maxHR": 175.0,
            "minHR": 120.0,
            "trainingEffectLabel": "THRESHOLD_WORK",
        }
    }
    activity_file = tmp_path / "activity.json"
    with open(activity_file, "w", encoding="utf-8") as f:
        json.dump(activity_data, f, ensure_ascii=False, indent=2)

    return hr_zones_file, activity_file


@pytest.fixture
def sample_hr_zones_file(tmp_path):
    """Create sample hr_zones.json file."""
    hr_zones = [
        {"zoneNumber": 1, "secsInZone": 88.001, "zoneLowBoundary": 116},
        {"zoneNumber": 2, "secsInZone": 576.894, "zoneLowBoundary": 130},
        {"zoneNumber": 3, "secsInZone": 1488.727, "zoneLowBoundary": 145},
        {"zoneNumber": 4, "secsInZone": 0.0, "zoneLowBoundary": 159},
        {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 174},
    ]

    hr_zones_file = tmp_path / "hr_zones.json"
    with open(hr_zones_file, "w", encoding="utf-8") as f:
        json.dump(hr_zones, f, ensure_ascii=False, indent=2)

    return hr_zones_file


@pytest.fixture
def sample_activity_file(tmp_path):
    """Create sample activity.json file."""
    activity_data = {
        "activityId": 20636804823,
        "summaryDTO": {
            "averageHR": 143.0,
            "maxHR": 156.0,
            "minHR": 70.0,
            "trainingEffectLabel": "AEROBIC_BASE",
        },
    }

    activity_file = tmp_path / "activity.json"
    with open(activity_file, "w", encoding="utf-8") as f:
        json.dump(activity_data, f, ensure_ascii=False, indent=2)

    return activity_file
