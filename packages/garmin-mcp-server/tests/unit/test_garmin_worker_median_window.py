"""Tests for GarminIngestWorker._calculate_median_weight window logic (#293).

Verifies that the 7-day median window [date-6, date] no longer requires the
target date to have a measurement: any single day with data in the window
yields a median, and only an entirely empty window returns None.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Create GarminIngestWorker instance with temporary directories."""
    monkeypatch.setattr("garmin_mcp.utils.paths.get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_raw_dir",
        lambda: tmp_path / "data" / "raw",
    )
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_weight_raw_dir",
        lambda: tmp_path / "data" / "raw" / "weight",
    )
    monkeypatch.setattr(
        "garmin_mcp.utils.paths.get_default_db_path",
        lambda: str(tmp_path / "test.duckdb"),
    )
    monkeypatch.setattr(
        "garmin_mcp.ingest.raw_data_fetcher.get_garmin_client",
        Mock(side_effect=ValueError("No credentials in test")),
    )

    worker = GarminIngestWorker()
    worker._ensure_dirs()
    yield worker


def _weight_payload(date_str: str, weight_kg: float) -> dict:
    """Build a minimal Garmin dateWeightList payload for a given date."""
    return {
        "startDate": date_str,
        "endDate": date_str,
        "dateWeightList": [
            {
                "calendarDate": date_str,
                "weight": int(weight_kg * 1000),  # grams
            }
        ],
    }


def _make_collector(weights_by_date: dict[str, float]):
    """Return a fake collect_body_composition_data keyed on date string."""

    def _collect(check_date_str: str):
        if check_date_str in weights_by_date:
            return _weight_payload(check_date_str, weights_by_date[check_date_str])
        return None

    return _collect


@pytest.mark.unit
class TestCalculateMedianWeightWindow:
    """Window-based behavior for _calculate_median_weight."""

    def test_median_weight_target_day_missing(self, worker):
        """Target day has no data; previous day weight=79.6 → weight_kg≈79.6."""
        target = "2025-10-10"
        prev = (
            datetime.strptime(target, "%Y-%m-%d") - timedelta(days=1)
        ).strftime("%Y-%m-%d")

        worker.collect_body_composition_data = Mock(
            side_effect=_make_collector({prev: 79.6})
        )

        result = worker._calculate_median_weight(target)

        assert result is not None
        assert result["date"] == target
        assert abs(result["weight_kg"] - 79.6) < 0.01
        assert result["sample_count"] == 1
        assert result["source"] == "7DAY_MEDIAN"

    def test_median_weight_window_median(self, worker):
        """Three days in window weight=[78.0, 79.0, 80.0] → median 79.0."""
        target = "2025-10-10"
        target_dt = datetime.strptime(target, "%Y-%m-%d")
        # Mix of target day and earlier days (target day included, others not).
        d_target = target  # i=0
        d_minus_2 = (target_dt - timedelta(days=2)).strftime("%Y-%m-%d")
        d_minus_5 = (target_dt - timedelta(days=5)).strftime("%Y-%m-%d")

        worker.collect_body_composition_data = Mock(
            side_effect=_make_collector(
                {d_target: 80.0, d_minus_2: 78.0, d_minus_5: 79.0}
            )
        )

        result = worker._calculate_median_weight(target)

        assert result is not None
        assert abs(result["weight_kg"] - 79.0) < 0.01
        assert result["sample_count"] == 3

    def test_median_weight_all_missing(self, worker):
        """Entire window [date-6, date] has no data → None."""
        target = "2025-10-10"

        worker.collect_body_composition_data = Mock(side_effect=_make_collector({}))

        result = worker._calculate_median_weight(target)

        assert result is None
