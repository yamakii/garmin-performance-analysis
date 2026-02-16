"""Tests for FitnessAssessor gap detection and DiagnosticReportGenerator."""

from __future__ import annotations

import pytest

from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor
from garmin_mcp.training_plan.models import FitnessSummary, PaceZones


def _make_assessor(
    mocker,
    activities,
    vo2_row=None,
    hz_rows=None,
    type_rows=None,
    pre_gap_vo2_row=None,
    baseline_activities=None,
):
    """Helper to create assessor with mocked DB.

    Args:
        pre_gap_vo2_row: If provided, adds an extra execute result for pre-gap VO2max query.
        baseline_activities: Pre-gap activities from 24-week lookback. If None and gap
            detected, defaults to pre-gap activities from the main activities list.
    """
    mock_conn = mocker.MagicMock()
    mock_ctx = mocker.MagicMock()
    mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
    mock_ctx.__exit__ = mocker.Mock(return_value=False)

    assessor = FitnessAssessor.__new__(FitnessAssessor)
    assessor.db_path = mocker.MagicMock()
    mocker.patch.object(assessor, "_get_connection", return_value=mock_ctx)

    # Build execute results in order matching assess() query sequence:
    # 1. activities (fetchall)
    # If gap detected: 2. baseline_activities 24-week (fetchall)
    # 3. vo2_max (fetchone), 4. heart_rate_zones (fetchall)
    # If gap detected: 5. pre-gap vo2_max (fetchone)
    # Last: hr_efficiency (fetchall)

    # Check if gap will be detected (7+ day gap between sorted activities)
    sorted_acts = sorted(activities, key=lambda r: r[1])
    has_gap = False
    gap_end_date = None
    if len(sorted_acts) >= 2:
        from datetime import datetime

        for i in range(1, len(sorted_acts)):
            prev = datetime.strptime(sorted_acts[i - 1][1], "%Y-%m-%d")
            curr = datetime.strptime(sorted_acts[i][1], "%Y-%m-%d")
            if (curr - prev).days >= 7:
                has_gap = True
                gap_end_date = sorted_acts[i][1]
                break

    results = [
        mocker.MagicMock(fetchall=mocker.Mock(return_value=activities)),
    ]

    if has_gap:
        # Baseline activities query (24-week lookback, before gap)
        if baseline_activities is None:
            baseline_activities = [a for a in sorted_acts if a[1] < gap_end_date]
        results.append(
            mocker.MagicMock(fetchall=mocker.Mock(return_value=baseline_activities))
        )

    results.append(mocker.MagicMock(fetchone=mocker.Mock(return_value=vo2_row)))
    results.append(mocker.MagicMock(fetchall=mocker.Mock(return_value=hz_rows or [])))

    if has_gap:
        # Pre-gap VO2max query result
        results.append(
            mocker.MagicMock(fetchone=mocker.Mock(return_value=pre_gap_vo2_row))
        )

    # Training type distribution
    results.append(mocker.MagicMock(fetchall=mocker.Mock(return_value=type_rows or [])))

    mock_conn.execute = mocker.Mock(side_effect=results)
    return assessor


@pytest.mark.unit
class TestGapDetection:
    """Tests for training gap detection in FitnessAssessor."""

    def test_no_gap_detected(self, mocker):
        """Activities every few days → no gap."""
        activities = [
            (1, "2026-02-01", 10.0, 3000, 300),
            (2, "2026-02-04", 8.0, 2400, 300),
            (3, "2026-02-07", 12.0, 3600, 300),
        ]
        assessor = _make_assessor(mocker, activities, vo2_row=(50.0,))
        summary = assessor.assess(lookback_weeks=8)

        assert summary.gap_detected is False
        assert summary.gap_weeks == 0
        assert summary.recent_runs == []

    def test_gap_detected_14_days(self, mocker):
        """14-day gap between activities → gap_detected=True, gap_weeks=2."""
        activities = [
            (1, "2026-01-10", 10.0, 3000, 300),
            (2, "2026-01-12", 8.0, 2400, 300),
            # 14-day gap
            (3, "2026-01-26", 4.0, 1500, 375),
            (4, "2026-01-28", 4.0, 1500, 375),
        ]
        assessor = _make_assessor(
            mocker, activities, vo2_row=(50.0,), pre_gap_vo2_row=(52.0,)
        )
        summary = assessor.assess(lookback_weeks=8)

        assert summary.gap_detected is True
        assert summary.gap_weeks == 2
        assert len(summary.recent_runs) == 2  # post-gap runs

    def test_pre_gap_volume_calculated(self, mocker):
        """Pre-gap weekly volume is calculated from activities before the gap."""
        activities = [
            (1, "2026-01-01", 10.0, 3000, 300),
            (2, "2026-01-03", 8.0, 2400, 300),
            (3, "2026-01-06", 12.0, 3600, 300),
            # 21-day gap
            (4, "2026-01-27", 4.0, 1500, 375),
        ]
        assessor = _make_assessor(
            mocker, activities, vo2_row=(50.0,), pre_gap_vo2_row=(52.0,)
        )
        summary = assessor.assess(lookback_weeks=8)

        assert summary.gap_detected is True
        assert summary.gap_weeks == 3
        assert summary.pre_gap_weekly_volume_km > 0
        # Pre-gap: 30km over 2 active ISO weeks (Jan 1 wk1, Jan 6 wk2)
        assert summary.pre_gap_weekly_volume_km == pytest.approx(15.0, abs=1.0)

    def test_pre_gap_vdot_from_vo2(self, mocker):
        """Pre-gap VDOT is derived from VO2max data before the gap."""
        activities = [
            (1, "2026-01-05", 10.0, 3000, 300),
            # 14-day gap
            (2, "2026-01-19", 4.0, 1500, 375),
        ]
        assessor = _make_assessor(
            mocker, activities, vo2_row=(50.0,), pre_gap_vo2_row=(52.0,)
        )
        summary = assessor.assess(lookback_weeks=8)

        assert summary.pre_gap_vdot is not None
        assert summary.pre_gap_vdot > 0

    def test_pre_gap_baseline_from_extended_lookback(self, mocker):
        """Pre-gap baseline uses 24-week lookback, not limited to lookback_weeks.

        Scenario: 8-week lookback contains only 1 pre-gap activity (Jan 15),
        but the 24-week window captures rich training history (Oct-Dec).
        """
        # Activities within 8-week lookback (what assess() fetches)
        activities = [
            (10, "2026-01-15", 8.0, 2400, 300),  # Only pre-gap run in 8w
            # 3-week gap
            (11, "2026-02-05", 4.0, 1500, 375),
            (12, "2026-02-08", 4.0, 1500, 375),
        ]

        # Baseline activities from 24-week lookback (Oct-Jan, before gap)
        baseline_activities = [
            (1, "2025-10-01", 12.0, 3600, 300),
            (2, "2025-10-05", 10.0, 3000, 300),
            (3, "2025-10-10", 15.0, 4500, 300),
            (4, "2025-10-15", 10.0, 3000, 300),
            (5, "2025-11-01", 12.0, 3600, 300),
            (6, "2025-11-05", 10.0, 3000, 300),
            (7, "2025-11-10", 15.0, 4500, 300),
            (8, "2025-12-01", 12.0, 3600, 300),
            (9, "2025-12-10", 10.0, 3000, 300),
            (10, "2026-01-15", 8.0, 2400, 300),
        ]

        assessor = _make_assessor(
            mocker,
            activities=activities,
            vo2_row=(46.0,),
            pre_gap_vo2_row=(46.0,),
            baseline_activities=baseline_activities,
        )
        summary = assessor.assess(lookback_weeks=8)

        assert summary.gap_detected is True
        # With 24-week baseline (114km over 9 active weeks), volume ~12.7 km/week
        assert summary.pre_gap_weekly_volume_km > 5.0
        assert summary.pre_gap_vdot is not None
        assert summary.pre_gap_vdot > 0

    def test_recent_runs_populated(self, mocker):
        """Post-gap runs are collected in recent_runs list."""
        activities = [
            (1, "2026-01-05", 10.0, 3000, 300),
            # 14-day gap
            (2, "2026-01-19", 4.06, 1500, 370),
            (3, "2026-01-21", 4.04, 1480, 366),
            (4, "2026-01-23", 3.83, 1400, 365),
        ]
        assessor = _make_assessor(
            mocker, activities, vo2_row=(50.0,), pre_gap_vo2_row=None
        )
        summary = assessor.assess(lookback_weeks=8)

        assert len(summary.recent_runs) == 3
        assert summary.recent_runs[0]["distance_km"] == 4.06
        assert summary.recent_runs[1]["distance_km"] == 4.04
        assert summary.recent_runs[2]["distance_km"] == 3.83


@pytest.mark.unit
class TestGapAwareVolumeCalculation:
    """Tests for gap-aware volume calculation in TrainingPlanGenerator."""

    def _make_fitness(
        self, gap_detected=False, weekly_volume=10.0, pre_gap_volume=32.5
    ):
        return FitnessSummary(
            vdot=45.0,
            pace_zones=PaceZones(
                easy_low=340.0,
                easy_high=300.0,
                marathon=270.0,
                threshold=255.0,
                interval=234.0,
                repetition=221.0,
            ),
            weekly_volume_km=weekly_volume,
            runs_per_week=3.0,
            gap_detected=gap_detected,
            gap_weeks=4,
            pre_gap_weekly_volume_km=pre_gap_volume,
        )

    def test_return_to_run_with_gap(self, mocker):
        """Gap detected: start from recent runs, peak = pre_gap*0.75."""
        fitness = self._make_fitness(
            gap_detected=True, weekly_volume=10.0, pre_gap_volume=32.5
        )
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = fitness

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=8,
            runs_per_week=3,
        )

        # No recent_runs → falls back to weekly_volume_km=10.0
        # start_km = max(10.0, 10.0) = 10.0
        assert plan.weekly_volume_start_km == 10.0
        # peak_km = max(10.0*1.1, 32.5*0.75) = max(11.0, 24.375) = 24.4
        assert plan.weekly_volume_peak_km == pytest.approx(24.4, abs=0.1)

    def test_return_to_run_without_gap(self, mocker):
        """No gap: uses standard conservative 1.3x calculation."""
        fitness = self._make_fitness(gap_detected=False, weekly_volume=30.0)
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = fitness

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        plan = generator.generate(
            goal_type="return_to_run",
            total_weeks=8,
            runs_per_week=3,
        )

        assert plan.weekly_volume_start_km == 30.0
        assert plan.weekly_volume_peak_km == pytest.approx(39.0, abs=0.1)

    def test_last_fitness_is_stored(self, mocker):
        """Generator stores last_fitness for diagnostic report."""
        fitness = self._make_fitness(gap_detected=True)
        mock_assessor = mocker.MagicMock()
        mock_assessor.assess.return_value = fitness

        mocker.patch(
            "garmin_mcp.training_plan.plan_generator.FitnessAssessor",
            return_value=mock_assessor,
        )
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
        )

        from garmin_mcp.training_plan.plan_generator import TrainingPlanGenerator

        generator = TrainingPlanGenerator(db_path=":memory:")
        generator.generate(goal_type="return_to_run", total_weeks=8, runs_per_week=3)

        assert generator.last_fitness is not None
        assert generator.last_fitness.gap_detected is True


@pytest.mark.unit
class TestDiagnosticReportGenerator:
    """Tests for DiagnosticReportGenerator."""

    def _make_fitness(self, gap_detected=False):
        return FitnessSummary(
            vdot=42.5,
            pace_zones=PaceZones(
                easy_low=360.0,
                easy_high=320.0,
                marathon=285.0,
                threshold=268.0,
                interval=248.0,
                repetition=234.0,
            ),
            weekly_volume_km=25.3,
            runs_per_week=3.5,
            training_type_distribution={
                "low_moderate": 0.6,
                "tempo_threshold": 0.2,
                "recovery": 0.2,
            },
            gap_detected=gap_detected,
            gap_weeks=4 if gap_detected else 0,
            pre_gap_weekly_volume_km=32.5 if gap_detected else 0,
            pre_gap_vdot=47.3 if gap_detected else None,
            recent_runs=(
                [
                    {"date": "2026-02-10", "distance_km": 4.06, "pace": 370.0},
                    {"date": "2026-02-12", "distance_km": 4.04, "pace": 366.0},
                    {"date": "2026-02-14", "distance_km": 3.83, "pace": 365.0},
                ]
                if gap_detected
                else []
            ),
        )

    def test_generate_normal(self):
        """Normal report without gap."""
        from garmin_mcp.training_plan.diagnostic_report import (
            DiagnosticReportGenerator,
        )

        gen = DiagnosticReportGenerator()
        fitness = self._make_fitness(gap_detected=False)
        content = gen.generate(
            fitness=fitness,
            goal_type="return_to_run",
            plan_params={"start_km": 25.3, "peak_km": 38.0},
        )

        assert "フィットネス診断レポート" in content
        assert "VDOT: 42.5" in content
        assert "25.3km" in content
        assert "休養期間" not in content

    def test_generate_with_gap(self):
        """Gap report includes gap details."""
        from garmin_mcp.training_plan.diagnostic_report import (
            DiagnosticReportGenerator,
        )

        gen = DiagnosticReportGenerator()
        fitness = self._make_fitness(gap_detected=True)
        content = gen.generate(
            fitness=fitness,
            goal_type="return_to_run",
            plan_params={"start_km": 15.0, "peak_km": 24.4},
        )

        assert "休養期間を検知" in content
        assert "約4週間" in content
        assert "32.5km" in content
        assert "復帰ラン: 3回" in content
        assert "75%（24.4km/週）" in content

    def test_save_creates_file(self, tmp_path, monkeypatch):
        """Save creates markdown file in diagnostics directory."""
        from garmin_mcp.training_plan.diagnostic_report import (
            DiagnosticReportGenerator,
        )

        monkeypatch.setattr(
            "garmin_mcp.utils.paths.get_result_dir",
            lambda: tmp_path,
        )

        gen = DiagnosticReportGenerator()
        result = gen.save("# Test Report", report_date="2026-02-16")

        assert "path" in result
        from pathlib import Path

        saved = Path(result["path"])
        assert saved.exists()
        assert saved.name == "2026-02-16_fitness_diagnostic.md"
        assert saved.parent.name == "diagnostics"
        assert saved.read_text() == "# Test Report"
