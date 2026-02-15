"""Tests for form_baseline.utils module."""

import pandas as pd
import pytest

from garmin_mcp.form_baseline.utils import drop_outliers, to_speed


class TestDropOutliers:
    """Test outlier removal with IQR method."""

    def test_drop_outliers_gct(self):
        """Test GCT outlier removal (100-400ms range)."""
        df = pd.DataFrame(
            {
                "gct_ms": [50, 150, 200, 250, 300, 350, 500],  # 50, 500 are outliers
                "other": [1, 2, 3, 4, 5, 6, 7],
            }
        )
        result = drop_outliers(df, column="gct_ms", valid_range=(100, 400))

        assert len(result) == 5
        assert result["gct_ms"].min() >= 100
        assert result["gct_ms"].max() <= 400
        assert 50 not in result["gct_ms"].values
        assert 500 not in result["gct_ms"].values

    def test_drop_outliers_vo(self):
        """Test VO outlier removal (2-15cm range)."""
        df = pd.DataFrame(
            {
                "vo_cm": [1.0, 5.0, 8.0, 10.0, 12.0, 20.0],  # 1.0, 20.0 are outliers
                "other": [1, 2, 3, 4, 5, 6],
            }
        )
        result = drop_outliers(df, column="vo_cm", valid_range=(2, 15))

        assert len(result) == 4
        assert result["vo_cm"].min() >= 2.0
        assert result["vo_cm"].max() <= 15.0

    def test_drop_outliers_speed(self):
        """Test speed outlier removal (1.5-7.0 m/s range)."""
        df = pd.DataFrame(
            {
                "speed_mps": [1.0, 2.5, 3.5, 4.5, 5.5, 8.0],  # 1.0, 8.0 are outliers
                "other": [1, 2, 3, 4, 5, 6],
            }
        )
        result = drop_outliers(df, column="speed_mps", valid_range=(1.5, 7.0))

        assert len(result) == 4
        assert result["speed_mps"].min() >= 1.5
        assert result["speed_mps"].max() <= 7.0

    def test_drop_outliers_empty_result(self):
        """Test when all data are outliers."""
        df = pd.DataFrame(
            {"gct_ms": [50, 60, 70], "other": [1, 2, 3]}  # All below 100ms
        )
        result = drop_outliers(df, column="gct_ms", valid_range=(100, 400))

        assert len(result) == 0

    def test_drop_outliers_no_outliers(self):
        """Test when no outliers exist."""
        df = pd.DataFrame(
            {"gct_ms": [200, 220, 240, 260, 280], "other": [1, 2, 3, 4, 5]}
        )
        result = drop_outliers(df, column="gct_ms", valid_range=(100, 400))

        assert len(result) == 5


class TestToSpeed:
    """Test pace to speed conversion."""

    def test_to_speed_normal_pace(self):
        """Test conversion for normal running pace."""
        # 5:00/km = 300 sec/km = 3.333 m/s
        speed = to_speed(300.0)
        assert abs(speed - 3.333) < 0.01

    def test_to_speed_fast_pace(self):
        """Test conversion for fast pace."""
        # 4:00/km = 240 sec/km = 4.167 m/s
        speed = to_speed(240.0)
        assert abs(speed - 4.167) < 0.01

    def test_to_speed_easy_pace(self):
        """Test conversion for easy pace."""
        # 7:00/km = 420 sec/km = 2.381 m/s
        speed = to_speed(420.0)
        assert abs(speed - 2.381) < 0.01

    def test_to_speed_zero_error(self):
        """Test error handling for zero pace."""
        with pytest.raises(ValueError, match="Pace must be positive"):
            to_speed(0.0)

    def test_to_speed_negative_error(self):
        """Test error handling for negative pace."""
        with pytest.raises(ValueError, match="Pace must be positive"):
            to_speed(-100.0)
