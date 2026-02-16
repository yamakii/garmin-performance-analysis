"""Tests for FitnessAssessor class."""

import pytest

from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor


@pytest.mark.unit
class TestFitnessAssessor:
    def _make_assessor(
        self, mocker, activities, vo2_row=None, lt_row=None, type_rows=None
    ):
        """Helper to create assessor with mocked DB."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        assessor = FitnessAssessor.__new__(FitnessAssessor)
        assessor.db_path = mocker.MagicMock()
        mocker.patch.object(assessor, "_get_connection", return_value=mock_ctx)

        # Mock execute calls in order:
        # 1. activities, 2. vo2_max, 3. lactate_threshold, 4. hr_efficiency
        results = [
            mocker.MagicMock(fetchall=mocker.Mock(return_value=activities)),
            mocker.MagicMock(fetchone=mocker.Mock(return_value=vo2_row)),
            mocker.MagicMock(fetchone=mocker.Mock(return_value=lt_row)),
            mocker.MagicMock(fetchall=mocker.Mock(return_value=type_rows or [])),
        ]
        mock_conn.execute = mocker.Mock(side_effect=results)
        return assessor

    def test_assess_with_full_data(self, mocker):
        """Normal case: VO2max + LT + activities available."""
        activities = [
            (1, "2026-02-01", 10.0, 3000, 300),
            (2, "2026-02-04", 8.0, 2400, 300),
            (3, "2026-02-07", 12.0, 3600, 300),
        ]
        assessor = self._make_assessor(
            mocker,
            activities=activities,
            vo2_row=(52.5,),
            lt_row=(165,),
            type_rows=[("low_moderate", 2), ("tempo_threshold", 1)],
        )

        summary = assessor.assess(lookback_weeks=8)

        assert summary.vdot > 0
        assert summary.weekly_volume_km == 3.8  # 30km / 8 weeks
        assert summary.runs_per_week == 0.4  # 3 / 8
        assert summary.pace_zones is not None
        assert summary.hr_zones is not None
        assert "low_moderate" in summary.training_type_distribution

    def test_assess_no_activities_raises(self, mocker):
        """Should raise ValueError when no activities found."""
        assessor = self._make_assessor(mocker, activities=[])

        with pytest.raises(ValueError, match="No running activities"):
            assessor.assess()

    def test_assess_no_vo2max_uses_performance(self, mocker):
        """Falls back to race performance when no VO2max."""
        activities = [
            (1, "2026-02-01", 10.0, 3000, 300),
            (2, "2026-02-04", 5.0, 1200, 240),  # faster pace
        ]
        assessor = self._make_assessor(
            mocker,
            activities=activities,
            vo2_row=None,
            lt_row=None,
        )

        summary = assessor.assess()

        assert summary.vdot > 0
        assert summary.hr_zones is None  # No LT data

    def test_assess_vo2max_no_lt(self, mocker):
        """VO2max available but no LT data."""
        activities = [
            (1, "2026-02-01", 10.0, 3000, 300),
        ]
        assessor = self._make_assessor(
            mocker,
            activities=activities,
            vo2_row=(50.0,),
            lt_row=None,
        )

        summary = assessor.assess()

        assert summary.vdot > 0
        assert summary.pace_zones is not None
        assert summary.hr_zones is None
