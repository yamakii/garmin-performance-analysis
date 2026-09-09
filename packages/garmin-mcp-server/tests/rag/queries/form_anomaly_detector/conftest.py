"""Fixtures shared by the form_anomaly_detector tests (split from test_form_anomaly_detector.py, #1069)."""

import json
from pathlib import Path

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector


@pytest.fixture
def base_path() -> Path:
    """Provide base path to test fixtures."""
    return Path(__file__).resolve().parents[3] / "fixtures" / "data"


@pytest.fixture
def detector(base_path: Path) -> FormAnomalyDetector:
    """Create FormAnomalyDetector instance with test base path."""
    return FormAnomalyDetector(base_path=base_path)


@pytest.fixture
def sample_activity_details(base_path: Path) -> dict[str, object]:
    """Load sample activity_details.json fixture."""
    file_path = (
        base_path
        / "data"
        / "raw"
        / "activity"
        / "12345678901"
        / "activity_details.json"
    )
    with open(file_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)
        return data


@pytest.fixture
def sample_performance_data(base_path: Path) -> dict[str, object]:
    """Load sample performance.json fixture."""
    file_path = base_path / "data" / "performance" / "12345678901.json"
    with open(file_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)
        return data
