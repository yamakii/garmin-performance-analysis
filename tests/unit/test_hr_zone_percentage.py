"""
Unit tests for HR zone percentage calculation in GarminIngestWorker.

Tests the _calculate_hr_efficiency_analysis() method's zone percentage calculation.
"""

from typing import Any

import pandas as pd
import pytest

from tools.ingest.garmin_worker import GarminIngestWorker


class TestHRZonePercentageCalculation:
    """Test HR zone percentage calculation in _calculate_hr_efficiency_analysis."""

    def test_calculate_hr_efficiency_analysis_with_zone_percentages(self):
        """Test that zone percentages are correctly calculated from hr_zones."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame(
            {
                "avg_heart_rate": [150, 155, 160],
            }
        )
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 600, "zoneLowBoundary": 0},
            {"zoneNumber": 2, "secsInZone": 1200, "zoneLowBoundary": 120},
            {"zoneNumber": 3, "secsInZone": 1800, "zoneLowBoundary": 140},
            {"zoneNumber": 4, "secsInZone": 300, "zoneLowBoundary": 160},
            {"zoneNumber": 5, "secsInZone": 100, "zoneLowBoundary": 180},
        ]
        # Total time: 4000 seconds

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - zone percentages should be calculated
        assert "zone1_percentage" in result
        assert "zone2_percentage" in result
        assert "zone3_percentage" in result
        assert "zone4_percentage" in result
        assert "zone5_percentage" in result

        # Expected percentages: 600/4000=15%, 1200/4000=30%, 1800/4000=45%, 300/4000=7.5%, 100/4000=2.5%
        assert result["zone1_percentage"] == pytest.approx(15.0, rel=0.01)
        assert result["zone2_percentage"] == pytest.approx(30.0, rel=0.01)
        assert result["zone3_percentage"] == pytest.approx(45.0, rel=0.01)
        assert result["zone4_percentage"] == pytest.approx(7.5, rel=0.01)
        assert result["zone5_percentage"] == pytest.approx(2.5, rel=0.01)

    def test_zone_percentage_sum_equals_100(self):
        """Test that all zone percentages sum to approximately 100%."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame({"avg_heart_rate": [145, 150, 155]})
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 500, "zoneLowBoundary": 0},
            {"zoneNumber": 2, "secsInZone": 1000, "zoneLowBoundary": 120},
            {"zoneNumber": 3, "secsInZone": 1500, "zoneLowBoundary": 140},
            {"zoneNumber": 4, "secsInZone": 800, "zoneLowBoundary": 160},
            {"zoneNumber": 5, "secsInZone": 200, "zoneLowBoundary": 180},
        ]

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - sum should be approximately 100%
        total_percentage = (
            result.get("zone1_percentage", 0)
            + result.get("zone2_percentage", 0)
            + result.get("zone3_percentage", 0)
            + result.get("zone4_percentage", 0)
            + result.get("zone5_percentage", 0)
        )
        assert total_percentage == pytest.approx(100.0, abs=0.1)

    def test_calculate_hr_efficiency_analysis_empty_zones(self):
        """Test that empty hr_zones doesn't cause errors."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame({"avg_heart_rate": [150, 155, 160]})
        hr_zones: list[dict[str, Any]] = []

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - should return basic fields without zone percentages
        assert "avg_heart_rate" in result
        assert "training_type" in result
        assert "hr_stability" in result
        # Zone percentages should not exist
        assert "zone1_percentage" not in result
        assert "zone2_percentage" not in result

    def test_calculate_hr_efficiency_analysis_zero_total_time(self):
        """Test that zero total time is handled correctly."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame({"avg_heart_rate": [150, 155, 160]})
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 0, "zoneLowBoundary": 0},
            {"zoneNumber": 2, "secsInZone": 0, "zoneLowBoundary": 120},
            {"zoneNumber": 3, "secsInZone": 0, "zoneLowBoundary": 140},
        ]

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - should not include zone percentages when total time is 0
        assert "zone1_percentage" not in result
        assert "zone2_percentage" not in result
        assert "zone3_percentage" not in result

    def test_calculate_hr_efficiency_analysis_missing_zone_number(self):
        """Test that missing zoneNumber is handled gracefully."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame({"avg_heart_rate": [150, 155, 160]})
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 1000, "zoneLowBoundary": 0},
            {"secsInZone": 500, "zoneLowBoundary": 120},  # Missing zoneNumber
            {"zoneNumber": 3, "secsInZone": 1500, "zoneLowBoundary": 140},
        ]

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - should only calculate percentages for valid zones
        assert "zone1_percentage" in result
        assert "zone2_percentage" not in result  # Missing zoneNumber
        assert "zone3_percentage" in result

    def test_calculate_hr_efficiency_analysis_rounding(self):
        """Test that percentages are rounded to 2 decimal places."""
        # Arrange
        worker = GarminIngestWorker()
        df = pd.DataFrame({"avg_heart_rate": [150, 155, 160]})
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 333, "zoneLowBoundary": 0},
            {"zoneNumber": 2, "secsInZone": 334, "zoneLowBoundary": 120},
            {"zoneNumber": 3, "secsInZone": 333, "zoneLowBoundary": 140},
        ]
        # Total: 1000 seconds

        # Act
        result = worker._calculate_hr_efficiency_analysis(df, hr_zones)

        # Assert - should be rounded to 2 decimal places
        assert result["zone1_percentage"] == 33.3
        assert result["zone2_percentage"] == 33.4
        assert result["zone3_percentage"] == 33.3
