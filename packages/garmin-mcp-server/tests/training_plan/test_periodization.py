"""Tests for PeriodizationEngine."""

import pytest

from garmin_mcp.training_plan.models import GoalType, PeriodizationPhase
from garmin_mcp.training_plan.periodization import PeriodizationEngine


@pytest.mark.unit
class TestCreateRacePhases:
    @pytest.mark.parametrize(
        "goal_type",
        [GoalType.RACE_5K, GoalType.RACE_10K, GoalType.RACE_HALF, GoalType.RACE_FULL],
    )
    def test_phases_sum_to_total_weeks(self, goal_type):
        for total_weeks in [8, 12, 16, 20]:
            phases = PeriodizationEngine.create_race_phases(total_weeks, goal_type)
            actual = sum(w for _, w in phases)
            assert actual == total_weeks

    def test_four_phases_present(self):
        phases = PeriodizationEngine.create_race_phases(12, GoalType.RACE_5K)
        phase_types = [p for p, _ in phases]
        assert PeriodizationPhase.BASE in phase_types
        assert PeriodizationPhase.BUILD in phase_types
        assert PeriodizationPhase.PEAK in phase_types
        assert PeriodizationPhase.TAPER in phase_types

    def test_minimum_one_week_per_phase(self):
        phases = PeriodizationEngine.create_race_phases(4, GoalType.RACE_5K)
        for _, weeks in phases:
            assert weeks >= 1

    def test_5k_base_is_largest(self):
        phases = PeriodizationEngine.create_race_phases(16, GoalType.RACE_5K)
        phase_dict = dict(phases)
        assert (
            phase_dict[PeriodizationPhase.BASE] >= phase_dict[PeriodizationPhase.BUILD]
        )


@pytest.mark.unit
class TestCreateFitnessPhases:
    def test_12_weeks_creates_3_mesocycles(self):
        phases = PeriodizationEngine.create_fitness_phases(12)
        assert sum(w for _, w in phases) == 12
        build_count = sum(1 for p, _ in phases if p == PeriodizationPhase.BUILD)
        recovery_count = sum(1 for p, _ in phases if p == PeriodizationPhase.RECOVERY)
        assert build_count == 3
        assert recovery_count == 3

    def test_total_weeks_matches_input(self):
        for total in [5, 8, 10, 12, 16]:
            phases = PeriodizationEngine.create_fitness_phases(total)
            assert sum(w for _, w in phases) == total


@pytest.mark.unit
class TestWeeklyVolumeProgression:
    def test_length_matches_total_weeks(self):
        phases = PeriodizationEngine.create_race_phases(12, GoalType.RACE_5K)
        volumes = PeriodizationEngine.weekly_volume_progression(20.0, 50.0, phases)
        total_weeks = sum(w for _, w in phases)
        assert len(volumes) == total_weeks

    def test_starts_near_start_km(self):
        phases = [(PeriodizationPhase.BASE, 8)]
        volumes = PeriodizationEngine.weekly_volume_progression(20.0, 50.0, phases)
        assert abs(volumes[0] - 20.0) < 1.0

    def test_taper_decreases(self):
        phases = [
            (PeriodizationPhase.BASE, 4),
            (PeriodizationPhase.BUILD, 4),
            (PeriodizationPhase.TAPER, 4),
        ]
        volumes = PeriodizationEngine.weekly_volume_progression(20.0, 50.0, phases)
        taper_vols = volumes[8:]
        for i in range(1, len(taper_vols)):
            assert taper_vols[i] <= taper_vols[i - 1]

    def test_recovery_weeks_lower(self):
        phases = [(PeriodizationPhase.BASE, 8)]
        volumes = PeriodizationEngine.weekly_volume_progression(20.0, 50.0, phases)
        # Week 4 (index 3) should be recovery
        assert volumes[3] < volumes[2]

    def test_empty_phases_returns_empty(self):
        assert PeriodizationEngine.weekly_volume_progression(20.0, 50.0, []) == []
