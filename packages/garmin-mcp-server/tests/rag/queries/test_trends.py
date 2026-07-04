"""Tests for PerformanceTrendAnalyzer.

The analyzer's regression x-axis is date-based (days since the earliest
activity), so the mocked reader provides ``get_activity_dates`` alongside the
bulk metric averages. Filtering uses ``get_bulk_activity_fields`` (a single
bulk query) rather than per-activity reader calls.
"""

import math
from unittest.mock import patch

import pytest

from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer


def _dates_for(activity_ids: list[int], start_day: int = 1) -> dict[int, str]:
    """Build evenly-spaced January 2025 dates following activity_ids order."""
    return {aid: f"2025-01-{start_day + i:02d}" for i, aid in enumerate(activity_ids)}


class TestPerformanceTrendAnalyzer:
    """Test PerformanceTrendAnalyzer functionality."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance with mocked DB."""
        with patch("garmin_mcp.rag.queries.trends.GarminDBReader") as mock_reader:
            analyzer = PerformanceTrendAnalyzer()
            analyzer.db_reader = mock_reader.return_value
            return analyzer

    @pytest.mark.unit
    def test_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.db_reader is not None

    @pytest.mark.unit
    def test_analyze_metric_trend_improving(self, analyzer):
        """Test improving pace trend detection."""
        # Mock bulk query: improving (decreasing) pace
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 310.0,
            2: 305.0,
            3: 300.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result is not None
        assert result["metric"] == "pace"
        assert result["trend"] == "improving"
        assert result["slope"] < 0  # Decreasing pace is improving
        assert result["data_points"] == 3
        # Verify single bulk call instead of per-activity calls
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "pace_seconds_per_km"
        )

    @pytest.mark.unit
    def test_analyze_metric_trend_declining(self, analyzer):
        """Test declining pace trend detection."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 305.0,
            3: 310.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "declining"
        assert result["slope"] > 0  # Increasing pace is declining

    @pytest.mark.unit
    def test_analyze_metric_trend_stable(self, analyzer):
        """Test stable trend detection (p-value > 0.05)."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 301.0,
            3: 299.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "stable"

    @pytest.mark.unit
    def test_trend_insufficient_data(self, analyzer):
        """Single data point yields insufficient_data."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {1: 300.0}
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1])

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1],
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 1

    @pytest.mark.unit
    def test_analyze_metric_trend_two_points_insufficient_data(self, analyzer):
        """Two points must NOT classify: linregress p=nan bypasses the gate.

        With exactly 2 observations scipy.stats.linregress returns
        ``p_value == nan`` (df=0), and ``nan > 0.05`` is False, so the pre-fix
        code would confidently report improving/declining. The >=3 guard now
        returns the insufficient_data shape instead.
        """
        analyzer.db_reader.get_bulk_metric_averages.return_value = {1: 5.2, 2: 4.8}
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",  # day 0
            2: "2025-01-04",  # day 3
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2],
        )

        assert result["trend"] == "insufficient_data"
        assert result["slope"] == 0.0
        assert result["data_points"] == 2

    @pytest.mark.unit
    def test_analyze_metric_trend_three_points_classifies(self, analyzer):
        """Three points restore the significance gate: p_value is finite.

        Regression-protects the n>=3 behavior: with 3 observations linregress
        yields a real (non-nan) p_value and the trend is classified normally.
        """
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 5.2,
            2: 5.0,
            3: 4.8,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",  # day 0
            2: "2025-01-03",  # day 2
            3: "2025-01-06",  # day 5
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert not math.isnan(result["p_value"])
        assert result["trend"] in {"stable", "improving", "declining"}
        assert result["data_points"] == 3

    @pytest.mark.unit
    def test_analyze_metric_heart_rate(self, analyzer):
        """Test heart rate trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 155.0,
            2: 152.0,
            3: 150.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="heart_rate",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "heart_rate"
        assert result["slope"] < 0
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "heart_rate"
        )

    @pytest.mark.unit
    def test_analyze_metric_form_metrics(self, analyzer):
        """Test form metrics (GCT) trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 250.0,
            2: 245.0,
            3: 240.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="ground_contact_time",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "ground_contact_time"
        assert result["data_points"] == 3
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "ground_contact_time"
        )

    @pytest.mark.unit
    def test_analyze_metric_elevation(self, analyzer):
        """Test elevation gain trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 100.0,
            2: 120.0,
            3: 140.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="elevation_gain",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "elevation_gain"
        assert result["slope"] > 0
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [1, 2, 3], "elevation_gain"
        )

    @pytest.mark.unit
    def test_analyze_metric_vertical_oscillation(self, analyzer):
        """Test vertical oscillation trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 9.5,
            2: 9.2,
            3: 9.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="vertical_oscillation",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "vertical_oscillation"
        assert result["data_points"] == 3

    @pytest.mark.unit
    def test_analyze_metric_vertical_ratio(self, analyzer):
        """Test vertical ratio trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 8.5,
            2: 8.2,
            3: 8.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="vertical_ratio",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "vertical_ratio"
        assert result["data_points"] == 3

    @pytest.mark.unit
    def test_analyze_metric_cadence(self, analyzer):
        """Test cadence trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 180.0,
            2: 182.0,
            3: 184.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="cadence",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "cadence"
        assert result["data_points"] == 3
        assert result["slope"] > 0  # Increasing cadence

    @pytest.mark.unit
    def test_analyze_metric_power(self, analyzer):
        """Test power trend analysis."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 250.0,
            2: 255.0,
            3: 260.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3])

        result = analyzer.analyze_metric_trend(
            metric="power",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["metric"] == "power"
        assert result["data_points"] == 3
        assert result["slope"] > 0  # Increasing power

    @pytest.mark.unit
    def test_trends_slope_golden(self, analyzer):
        """Golden: a fixed pace series freezes the per-day regression slope.

        Pace 310, 305, 304, 300, 296 on consecutive days (Jan 1-5 -> x = 0..4)
        regresses to a slope of exactly -3.3 s/km per day (Sxy=-33, Sxx=10) with
        correlation ~-0.986. This guards the date-based regression coefficient
        against silent drift; recompute deliberately if the regression axis or
        method is intentionally changed.
        """
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 310.0,
            2: 305.0,
            3: 304.0,
            4: 300.0,
            5: 296.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2, 3, 4, 5])

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3, 4, 5],
        )

        assert result["slope"] == pytest.approx(-3.3, abs=1e-6)
        assert result["correlation"] == pytest.approx(-0.986064, abs=1e-5)
        assert result["trend"] == "improving"
        assert result["data_points"] == 5

    @pytest.mark.unit
    def test_unsupported_metric(self, analyzer):
        """Test unsupported metric handling."""
        with pytest.raises(ValueError, match="Unsupported metric"):
            analyzer.analyze_metric_trend(
                metric="invalid_metric",
                start_date="2025-01-01",
                end_date="2025-01-31",
                activity_ids=[1, 2, 3],
            )

    @pytest.mark.unit
    def test_empty_metric_data(self, analyzer):
        """Test handling of empty metric data."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {}
        analyzer.db_reader.get_activity_dates.return_value = {}

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["trend"] == "insufficient_data"
        assert result["data_points"] == 0

    @pytest.mark.unit
    def test_missing_activity_in_bulk_result(self, analyzer):
        """Test that missing activities in bulk result are skipped."""
        # Activity 2 has no metric data
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 310.0,
            3: 300.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",
            3: "2025-01-03",
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
        )

        assert result["data_points"] == 2

    @pytest.mark.unit
    def test_activity_type_filter_not_silent_noop(self, analyzer):
        """activity_type must raise NotImplementedError, never silently pass."""
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 305.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = _dates_for([1, 2])

        with pytest.raises(NotImplementedError, match="activity_type"):
            analyzer.analyze_metric_trend(
                metric="pace",
                start_date="2025-01-01",
                end_date="2025-01-31",
                activity_ids=[1, 2],
                activity_type="aerobic_base",
            )

        # Filtering raised before any metric extraction happened.
        analyzer.db_reader.get_bulk_metric_averages.assert_not_called()

    @pytest.mark.unit
    def test_summarize_metric_period_medians_and_delta(self, analyzer):
        """Descriptive summary: medians + previous-week delta, no regression."""
        analyzer.db_reader.get_bulk_metric_averages.side_effect = [
            {1: 5.5, 2: 5.4, 3: 5.6},  # current week
            {4: 5.7, 5: 5.6, 6: 5.8},  # previous week
        ]

        result = analyzer.summarize_metric_period(
            metric="pace",
            activity_ids=[1, 2, 3],
            prev_activity_ids=[4, 5, 6],
        )

        assert result["mode"] == "descriptive"
        assert result["median"] == pytest.approx(5.5)
        assert result["prev_period_median"] == pytest.approx(5.7)
        assert result["delta_pct"] == pytest.approx(-3.5, abs=0.1)
        assert result["data_points"] == 3
        assert result["prev_data_points"] == 3
        # No regression keys at week granularity.
        assert "slope" not in result
        assert "p_value" not in result
        assert "trend" not in result

    @pytest.mark.unit
    def test_summarize_metric_period_empty_prev(self, analyzer):
        """No previous-week runs -> null baseline and null delta."""
        analyzer.db_reader.get_bulk_metric_averages.side_effect = [
            {1: 5.5, 2: 5.4},  # current week
            {},  # previous week: no runs
        ]

        result = analyzer.summarize_metric_period(
            metric="pace",
            activity_ids=[1, 2],
            prev_activity_ids=[],
        )

        assert result["prev_period_median"] is None
        assert result["delta_pct"] is None
        assert result["prev_data_points"] == 0
        assert result["data_points"] == 2
        assert result["median"] == pytest.approx(5.45)

    @pytest.mark.integration
    def test_trend_uses_date_axis_not_index(self, analyzer):
        """Regression uses activity_date order, not the activity_ids order.

        activity_ids are passed in a date-shuffled order. By index the pace
        would look increasing (declining), but in true chronological order it
        decreases (improving). The date-based x-axis must yield "improving".
        """
        # activity_ids order: [3, 1, 2]
        # Dates: id 1 = Jan 1, id 2 = Jan 2, id 3 = Jan 3 (chronological by id)
        # Values by id: id 1 = 320, id 2 = 310, id 3 = 300
        # Chronological (Jan1->Jan3): 320, 310, 300 -> decreasing -> improving
        # Index order [3,1,2] values: 300, 320, 310 -> would NOT be improving
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            3: 300.0,
            1: 320.0,
            2: 310.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",
            2: "2025-01-02",
            3: "2025-01-03",
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[3, 1, 2],
        )

        assert result["trend"] == "improving"
        assert result["slope"] < 0

    @pytest.mark.integration
    def test_trend_unequal_date_intervals(self, analyzer):
        """Unequal date gaps use elapsed days, not uniform spacing.

        Activities at day 0, 1, 30, 90. Pace increases over real time, so the
        per-day slope must be positive (declining) and small in magnitude.
        """
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            2: 301.0,
            3: 320.0,
            4: 360.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",  # day 0
            2: "2025-01-02",  # day 1
            3: "2025-01-31",  # day 30
            4: "2025-04-01",  # day 90
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-04-01",
            activity_ids=[1, 2, 3, 4],
        )

        # Pace rising over ~90 days -> positive per-day slope -> declining.
        assert result["slope"] > 0
        assert result["trend"] == "declining"
        # Per-day slope is modest (60 sec over ~90 days), not the per-index
        # slope (~20 sec/step) the old index-based axis would have produced.
        assert result["slope"] < 5.0

    @pytest.mark.integration
    def test_distance_filter_uses_activities_table(self, analyzer):
        """distance_range filters via activities.total_distance_km."""
        analyzer.db_reader.get_bulk_activity_fields.return_value = {
            1: {"total_distance_km": 2.0},  # outside (5-10)
            2: {"total_distance_km": 7.0},  # within
            3: {"total_distance_km": 9.5},  # within
        }
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            2: 305.0,
            3: 310.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            2: "2025-01-02",
            3: "2025-01-03",
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
            distance_range=(5.0, 10.0),
        )

        # Only activities 2 and 3 pass the distance filter.
        assert result["data_points"] == 2
        analyzer.db_reader.get_bulk_activity_fields.assert_called_once_with(
            [1, 2, 3], ["total_distance_km"]
        )
        # The metric query received only the filtered IDs.
        analyzer.db_reader.get_bulk_metric_averages.assert_called_once_with(
            [2, 3], "pace_seconds_per_km"
        )
        # Old splits-based distance path is no longer used.
        analyzer.db_reader.get_splits_pace_hr.assert_not_called()

    @pytest.mark.integration
    def test_temperature_filter_bulk_no_n_plus_1(self, analyzer):
        """temperature_range uses one bulk query, no per-activity reads."""
        analyzer.db_reader.get_bulk_activity_fields.return_value = {
            1: {"temp_celsius": 15.0},  # within (10-20)
            2: {"temp_celsius": 25.0},  # outside
            3: {"temp_celsius": 18.0},  # within
        }
        analyzer.db_reader.get_bulk_metric_averages.return_value = {
            1: 300.0,
            3: 305.0,
        }
        analyzer.db_reader.get_activity_dates.return_value = {
            1: "2025-01-01",
            3: "2025-01-03",
        }

        result = analyzer.analyze_metric_trend(
            metric="pace",
            start_date="2025-01-01",
            end_date="2025-01-31",
            activity_ids=[1, 2, 3],
            temperature_range=(10.0, 20.0),
        )

        assert result["data_points"] == 2
        # Exactly one bulk call for the temperature field.
        analyzer.db_reader.get_bulk_activity_fields.assert_called_once_with(
            [1, 2, 3], ["temp_celsius"]
        )
        # No per-activity weather lookups (the old N+1 path).
        analyzer.db_reader.get_weather_data.assert_not_called()
