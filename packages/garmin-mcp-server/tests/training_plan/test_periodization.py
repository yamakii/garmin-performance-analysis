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


@pytest.mark.unit
class TestReturnToRunVolumeProgression:
    """Tests for recovery-dominant volume progression (return_to_run)."""

    @pytest.fixture()
    def return_to_run_8w_phases(self):
        """Standard 8-week return_to_run phases."""
        return PeriodizationEngine.create_return_to_run_phases(8)

    def test_return_to_run_volume_reaches_peak(self, return_to_run_8w_phases):
        """RECOVERY-dominant plan should reach near peak_km."""
        volumes = PeriodizationEngine.weekly_volume_progression(
            11.9, 21.6, return_to_run_8w_phases
        )
        assert (
            max(volumes) >= 19.0
        ), f"Peak volume {max(volumes):.1f}km is too far from target 21.6km"

    def test_return_to_run_monotonic_increase(self, return_to_run_8w_phases):
        """Pure linear progression should monotonically increase."""
        volumes = PeriodizationEngine.weekly_volume_progression(
            11.9, 21.6, return_to_run_8w_phases
        )
        for i in range(1, len(volumes)):
            assert (
                volumes[i] >= volumes[i - 1]
            ), f"Week {i+1} ({volumes[i]:.1f}) < Week {i} ({volumes[i-1]:.1f})"

    def test_race_plan_not_using_linear_path(self):
        """BASE/BUILD-dominant race plans should NOT use the linear path."""
        phases = PeriodizationEngine.create_race_phases(12, GoalType.RACE_10K)
        volumes = PeriodizationEngine.weekly_volume_progression(20.0, 50.0, phases)
        # Race plan uses 10% rule, so BASE/BUILD increments are capped at 2.0km
        # Verify the increment between first two weeks is <= 10% of start
        assert volumes[1] - volumes[0] <= 20.0 * 0.10 + 0.01
        # Verify it doesn't reach peak in BASE phase (10% rule limits it)
        base_weeks = dict(phases).get(PeriodizationPhase.BASE, 0)
        base_vols = volumes[:base_weeks]
        assert max(base_vols) < 50.0, "10% rule should prevent reaching peak in BASE"

    def test_return_to_run_length_matches(self, return_to_run_8w_phases):
        """Output length should match total weeks."""
        volumes = PeriodizationEngine.weekly_volume_progression(
            11.9, 21.6, return_to_run_8w_phases
        )
        total = sum(w for _, w in return_to_run_8w_phases)
        assert len(volumes) == total


@pytest.mark.unit
class TestCreateReturnToRunPhases:
    @pytest.mark.parametrize("total_weeks", [4, 6, 8, 10, 12])
    def test_phases_sum_to_total_weeks(self, total_weeks):
        phases = PeriodizationEngine.create_return_to_run_phases(total_weeks)
        actual = sum(w for _, w in phases)
        assert actual == total_weeks

    def test_4_weeks_recovery_then_base(self):
        phases = PeriodizationEngine.create_return_to_run_phases(4)
        phase_types = [p for p, _ in phases]
        # First phase should be RECOVERY
        assert phase_types[0] == PeriodizationPhase.RECOVERY
        # Should contain BASE
        assert PeriodizationPhase.BASE in phase_types
        # Should NOT contain BUILD, PEAK, or TAPER
        assert PeriodizationPhase.PEAK not in phase_types
        assert PeriodizationPhase.TAPER not in phase_types

    def test_4_weeks_no_threshold_or_interval_phases(self):
        """Short return-to-run plan should only have RECOVERY and BASE."""
        phases = PeriodizationEngine.create_return_to_run_phases(4)
        phase_types = {p for p, _ in phases}
        assert phase_types <= {PeriodizationPhase.RECOVERY, PeriodizationPhase.BASE}

    def test_8_weeks_starts_with_recovery(self):
        phases = PeriodizationEngine.create_return_to_run_phases(8)
        assert phases[0][0] == PeriodizationPhase.RECOVERY

    def test_8_weeks_has_base_phase(self):
        phases = PeriodizationEngine.create_return_to_run_phases(8)
        phase_types = [p for p, _ in phases]
        assert PeriodizationPhase.BASE in phase_types

    def test_12_weeks_has_build_phase(self):
        """Long return-to-run allows BUILD but no PEAK/TAPER."""
        phases = PeriodizationEngine.create_return_to_run_phases(12)
        phase_types = [p for p, _ in phases]
        assert PeriodizationPhase.BUILD in phase_types
        assert PeriodizationPhase.PEAK not in phase_types
        assert PeriodizationPhase.TAPER not in phase_types

    def test_all_weeks_positive(self):
        for total in [4, 6, 8, 10, 12]:
            phases = PeriodizationEngine.create_return_to_run_phases(total)
            for _, weeks in phases:
                assert weeks >= 1


@pytest.mark.unit
class TestFrequencyProgression:
    def test_linear_4_weeks(self):
        """start=3, target=6, weeks=4 → [3, 4, 5, 6]."""
        result = PeriodizationEngine.frequency_progression(3, 6, 4)
        assert result == [3, 4, 5, 6]

    def test_longer_8_weeks(self):
        """start=4, target=6, weeks=8 → gradual increase."""
        result = PeriodizationEngine.frequency_progression(4, 6, 8)
        assert len(result) == 8
        assert result[0] == 4
        assert result[-1] == 6
        # Monotonically non-decreasing
        for i in range(1, len(result)):
            assert result[i] >= result[i - 1]

    def test_same_start_target(self):
        """start=target → all same value."""
        result = PeriodizationEngine.frequency_progression(5, 5, 4)
        assert result == [5, 5, 5, 5]

    def test_clamp_to_valid_range(self):
        """Values should be clamped to 3-6."""
        result = PeriodizationEngine.frequency_progression(2, 7, 4)
        for v in result:
            assert 3 <= v <= 6

    def test_single_week(self):
        result = PeriodizationEngine.frequency_progression(3, 6, 1)
        assert result == [3]

    def test_empty_weeks(self):
        result = PeriodizationEngine.frequency_progression(3, 6, 0)
        assert result == []
