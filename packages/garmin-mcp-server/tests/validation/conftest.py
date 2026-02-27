"""Fixtures for validation tests."""

import pytest


@pytest.fixture
def valid_activity_data() -> dict:
    """Minimal valid activity record."""
    return {
        "activity_id": 12345,
        "activity_date": "2025-10-15",
        "activity_name": "Morning Run",
        "total_distance_km": 10.5,
        "total_time_seconds": 3600,
        "avg_speed_ms": 2.92,
        "avg_pace_seconds_per_km": 343,
        "avg_heart_rate": 150,
        "max_heart_rate": 175,
        "temp_celsius": 15.0,
        "relative_humidity_percent": 60.0,
        "wind_speed_kmh": 10.0,
        "wind_direction": "NW",
        "gear_type": "Running",
        "gear_model": "Nike Vaporfly",
        "base_weight_kg": 65.0,
    }


@pytest.fixture
def valid_split_data() -> dict:
    """Minimal valid split record."""
    return {
        "activity_id": 12345,
        "split_index": 0,
        "distance": 1.0,
        "duration_seconds": 300.0,
        "pace_seconds_per_km": 300.0,
        "heart_rate": 150,
        "cadence": 180.0,
        "ground_contact_time": 230.0,
        "vertical_oscillation": 8.5,
        "vertical_ratio": 7.0,
        "elevation_gain": 10.0,
        "elevation_loss": 5.0,
        "power": 250.0,
        "stride_length": 120.0,
        "max_heart_rate": 165,
        "max_cadence": 190.0,
        "max_power": 300.0,
        "normalized_power": 260.0,
        "average_speed": 3.33,
        "grade_adjusted_speed": 3.40,
    }
