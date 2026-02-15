"""Tests for WeeklyTemplateEngine."""

import pytest

from garmin_mcp.training_plan.models import (
    GoalType,
    PaceZones,
    PeriodizationPhase,
    WorkoutType,
)
from garmin_mcp.training_plan.weekly_templates import WeeklyTemplateEngine


@pytest.fixture
def pace_zones():
    return PaceZones(
        easy_low=360.0,
        easy_high=300.0,
        marathon=276.0,
        threshold=255.0,
        interval=234.0,
        repetition=221.0,
    )


@pytest.mark.unit
class TestGetWeeklyTemplate:
    @pytest.mark.parametrize("runs", [3, 4, 5, 6])
    def test_template_length_matches(self, runs):
        template = WeeklyTemplateEngine.get_weekly_template(
            runs, PeriodizationPhase.BASE, GoalType.RACE_5K
        )
        assert len(template) == runs

    def test_long_run_always_last(self):
        for runs in [3, 4, 5, 6]:
            template = WeeklyTemplateEngine.get_weekly_template(
                runs, PeriodizationPhase.BASE, GoalType.RACE_5K
            )
            assert template[-1] == WorkoutType.LONG_RUN

    def test_base_has_tempo(self):
        template = WeeklyTemplateEngine.get_weekly_template(
            4, PeriodizationPhase.BASE, GoalType.RACE_5K
        )
        assert WorkoutType.TEMPO in template

    def test_build_has_threshold(self):
        template = WeeklyTemplateEngine.get_weekly_template(
            4, PeriodizationPhase.BUILD, GoalType.RACE_5K
        )
        assert WorkoutType.THRESHOLD in template

    def test_build_5_has_threshold_and_interval(self):
        template = WeeklyTemplateEngine.get_weekly_template(
            5, PeriodizationPhase.BUILD, GoalType.RACE_5K
        )
        assert WorkoutType.THRESHOLD in template
        assert WorkoutType.INTERVAL in template

    def test_peak_has_interval(self):
        template = WeeklyTemplateEngine.get_weekly_template(
            4, PeriodizationPhase.PEAK, GoalType.RACE_5K
        )
        assert WorkoutType.INTERVAL in template

    def test_recovery_all_easy_or_long(self):
        template = WeeklyTemplateEngine.get_weekly_template(
            4, PeriodizationPhase.RECOVERY, GoalType.RACE_5K
        )
        for wt in template:
            assert wt in (WorkoutType.EASY, WorkoutType.LONG_RUN)

    def test_invalid_runs_raises(self):
        with pytest.raises(ValueError):
            WeeklyTemplateEngine.get_weekly_template(
                2, PeriodizationPhase.BASE, GoalType.RACE_5K
            )
        with pytest.raises(ValueError):
            WeeklyTemplateEngine.get_weekly_template(
                7, PeriodizationPhase.BASE, GoalType.RACE_5K
            )


@pytest.mark.unit
class TestFillWorkoutDetails:
    def test_returns_correct_count(self, pace_zones):
        types = [
            WorkoutType.EASY,
            WorkoutType.TEMPO,
            WorkoutType.EASY,
            WorkoutType.LONG_RUN,
        ]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BASE, 40.0, pace_zones
        )
        assert len(workouts) == 4

    def test_long_run_25_to_30_percent(self, pace_zones):
        types = [
            WorkoutType.EASY,
            WorkoutType.TEMPO,
            WorkoutType.EASY,
            WorkoutType.LONG_RUN,
        ]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BASE, 40.0, pace_zones
        )
        long_run = next(w for w in workouts if w.workout_type == WorkoutType.LONG_RUN)
        assert long_run.target_distance_km is not None
        assert 9.0 <= long_run.target_distance_km <= 13.0

    def test_easy_pace_targets(self, pace_zones):
        types = [WorkoutType.EASY, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BASE, 30.0, pace_zones
        )
        easy = next(w for w in workouts if w.workout_type == WorkoutType.EASY)
        assert easy.target_pace_low == pace_zones.easy_low
        assert easy.target_pace_high == pace_zones.easy_high

    def test_interval_has_details(self, pace_zones):
        types = [WorkoutType.EASY, WorkoutType.INTERVAL, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.PEAK, 40.0, pace_zones
        )
        interval = next(w for w in workouts if w.workout_type == WorkoutType.INTERVAL)
        assert interval.intervals is not None
        assert interval.intervals.repetitions == 5
        assert interval.intervals.work_distance_m == 1000

    def test_all_have_descriptions(self, pace_zones):
        types = [WorkoutType.EASY, WorkoutType.THRESHOLD, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BUILD, 40.0, pace_zones
        )
        for w in workouts:
            assert w.description_ja is not None
            assert len(w.description_ja) > 0

    def test_plan_id_and_week_set(self, pace_zones):
        types = [WorkoutType.EASY, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 5, "plan-xyz", PeriodizationPhase.BASE, 30.0, pace_zones
        )
        for w in workouts:
            assert w.plan_id == "plan-xyz"
            assert w.week_number == 5

    def test_low_volume_long_run_gte_quality(self, pace_zones):
        """At low volumes, long run should be >= quality workout distance."""
        types = [WorkoutType.EASY, WorkoutType.TEMPO, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BASE, 15.0, pace_zones
        )
        long_run = next(w for w in workouts if w.workout_type == WorkoutType.LONG_RUN)
        tempo = next(w for w in workouts if w.workout_type == WorkoutType.TEMPO)
        assert long_run.target_distance_km is not None
        assert tempo.target_distance_km is not None
        assert long_run.target_distance_km >= tempo.target_distance_km

    def test_quality_distance_scales_with_volume(self, pace_zones):
        """Quality distance should scale with weekly volume."""
        types_low = [WorkoutType.EASY, WorkoutType.TEMPO, WorkoutType.LONG_RUN]
        types_high = [WorkoutType.EASY, WorkoutType.TEMPO, WorkoutType.LONG_RUN]

        low_workouts = WeeklyTemplateEngine.fill_workout_details(
            types_low, 1, "plan-1", PeriodizationPhase.BASE, 15.0, pace_zones
        )
        high_workouts = WeeklyTemplateEngine.fill_workout_details(
            types_high, 1, "plan-1", PeriodizationPhase.BASE, 50.0, pace_zones
        )

        low_tempo = next(w for w in low_workouts if w.workout_type == WorkoutType.TEMPO)
        high_tempo = next(
            w for w in high_workouts if w.workout_type == WorkoutType.TEMPO
        )
        assert high_tempo.target_distance_km is not None
        assert low_tempo.target_distance_km is not None
        assert high_tempo.target_distance_km > low_tempo.target_distance_km

    def test_quality_distance_has_minimum(self, pace_zones):
        """Quality distance should not go below 3km even at very low volume."""
        types = [WorkoutType.EASY, WorkoutType.THRESHOLD, WorkoutType.LONG_RUN]
        workouts = WeeklyTemplateEngine.fill_workout_details(
            types, 1, "plan-1", PeriodizationPhase.BUILD, 10.0, pace_zones
        )
        threshold = next(w for w in workouts if w.workout_type == WorkoutType.THRESHOLD)
        assert threshold.target_distance_km is not None
        assert threshold.target_distance_km >= 3.0
