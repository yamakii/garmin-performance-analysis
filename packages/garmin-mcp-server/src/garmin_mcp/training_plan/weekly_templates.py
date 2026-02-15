"""Weekly workout template engine for training plan generation.

Handles workout type selection per phase and fills workout details
with pace targets, distances, and Japanese descriptions.
"""

from __future__ import annotations

from garmin_mcp.training_plan.models import (
    GoalType,
    HRZones,
    IntervalDetail,
    PaceZones,
    PeriodizationPhase,
    PlannedWorkout,
    WorkoutType,
)


class WeeklyTemplateEngine:
    """Engine for creating weekly workout schedules."""

    @staticmethod
    def get_weekly_template(
        runs_per_week: int,
        phase: PeriodizationPhase,
        goal_type: GoalType,
    ) -> list[WorkoutType]:
        """Return list of workout types for the week.

        Templates (by runs_per_week):
        3: [easy, quality, long_run]
        4: [easy, quality, easy, long_run]
        5: [easy, quality, easy, quality2, long_run]
        6: [easy, quality, easy, quality2, easy, long_run]

        Quality workout selection by phase:
        - Base: tempo
        - Build: threshold (primary), interval (secondary)
        - Peak: interval (primary), repetition (secondary)
        - Taper: threshold (1 short), rest easy
        - Recovery: all easy
        """
        if runs_per_week < 3 or runs_per_week > 6:
            raise ValueError(f"runs_per_week must be 3-6, got {runs_per_week}")

        # Determine quality workouts by phase
        # return_to_run: all easy regardless of phase (no tempo/threshold/interval)
        if goal_type == GoalType.RETURN_TO_RUN:
            q1, q2 = WorkoutType.EASY, WorkoutType.EASY
        elif phase == PeriodizationPhase.BASE:
            q1, q2 = WorkoutType.TEMPO, WorkoutType.TEMPO
        elif phase == PeriodizationPhase.BUILD:
            q1, q2 = WorkoutType.THRESHOLD, WorkoutType.INTERVAL
        elif phase == PeriodizationPhase.PEAK:
            q1, q2 = WorkoutType.INTERVAL, WorkoutType.REPETITION
        elif phase == PeriodizationPhase.TAPER:
            q1, q2 = WorkoutType.THRESHOLD, WorkoutType.EASY
        else:  # RECOVERY
            q1, q2 = WorkoutType.EASY, WorkoutType.EASY

        templates = {
            3: [WorkoutType.EASY, q1, WorkoutType.LONG_RUN],
            4: [WorkoutType.EASY, q1, WorkoutType.EASY, WorkoutType.LONG_RUN],
            5: [WorkoutType.EASY, q1, WorkoutType.EASY, q2, WorkoutType.LONG_RUN],
            6: [
                WorkoutType.EASY,
                q1,
                WorkoutType.EASY,
                q2,
                WorkoutType.EASY,
                WorkoutType.LONG_RUN,
            ],
        }

        return templates[runs_per_week]

    @staticmethod
    def fill_workout_details(
        workout_types: list[WorkoutType],
        week_number: int,
        plan_id: str,
        phase: PeriodizationPhase,
        weekly_volume_km: float,
        pace_zones: PaceZones,
        preferred_long_run_day: int = 7,
        hr_zones: HRZones | None = None,
        rest_days: list[int] | None = None,
    ) -> list[PlannedWorkout]:
        """Create PlannedWorkout instances with pace targets and distances.

        When hr_zones is provided, easy/long_run workouts use HR targets
        with time-based end conditions instead of pace targets with distance.

        Volume distribution:
        - Long run: 25-30% of weekly volume
        - Quality: 20% of weekly volume (min 3km), 15% for repetition (min 2km)
        - Easy runs: Split remaining volume equally
        """
        runs_per_week = len(workout_types)

        # Long run: 25% for 5+ runs, 30% for fewer
        long_run_pct = 0.25 if runs_per_week >= 5 else 0.30
        long_run_km = round(weekly_volume_km * long_run_pct, 1)

        # Quality workout distances: volume-proportional with minimums
        # Prevents long_run < quality inversion at low volumes
        quality_km = {
            WorkoutType.TEMPO: max(3.0, round(weekly_volume_km * 0.20, 1)),
            WorkoutType.THRESHOLD: max(3.0, round(weekly_volume_km * 0.20, 1)),
            WorkoutType.INTERVAL: max(3.0, round(weekly_volume_km * 0.20, 1)),
            WorkoutType.REPETITION: max(2.0, round(weekly_volume_km * 0.15, 1)),
        }

        # Calculate easy run distance
        total_quality = sum(
            quality_km.get(wt, 0)
            for wt in workout_types
            if wt not in (WorkoutType.EASY, WorkoutType.LONG_RUN)
        )
        easy_count = sum(1 for wt in workout_types if wt == WorkoutType.EASY)
        remaining = weekly_volume_km - long_run_km - total_quality
        easy_km = round(max(remaining / easy_count, 2.0), 1) if easy_count > 0 else 0

        # Ensure long run is the longest run of the week
        if easy_count > 0 and long_run_km < easy_km:
            # Redistribute: long_run = easy, then recalc easy from remaining
            long_run_km = easy_km
            remaining = weekly_volume_km - long_run_km - total_quality
            easy_km = round(max(remaining / easy_count, 3.0), 1)

        # Assign days: spread across week, long run on preferred day
        day_slots = _assign_days(runs_per_week, preferred_long_run_day, rest_days)

        workouts: list[PlannedWorkout] = []
        for i, wt in enumerate(workout_types):
            day = day_slots[i]

            if wt == WorkoutType.EASY:
                if hr_zones:
                    easy_pace_mid = (pace_zones.easy_low + pace_zones.easy_high) / 2
                    duration_min = round(easy_km * easy_pace_mid / 60 / 5) * 5
                    w = PlannedWorkout(
                        plan_id=plan_id,
                        week_number=week_number,
                        day_of_week=day,
                        workout_type=wt,
                        target_distance_km=easy_km,
                        target_duration_minutes=duration_min,
                        target_hr_low=hr_zones.easy_low,
                        target_hr_high=hr_zones.easy_high,
                        phase=phase,
                        description_ja=f"イージーラン {int(duration_min)}分",
                    )
                else:
                    w = PlannedWorkout(
                        plan_id=plan_id,
                        week_number=week_number,
                        day_of_week=day,
                        workout_type=wt,
                        target_distance_km=easy_km,
                        target_pace_low=pace_zones.easy_low,
                        target_pace_high=pace_zones.easy_high,
                        phase=phase,
                        description_ja=f"イージーラン {easy_km}km",
                    )
            elif wt == WorkoutType.LONG_RUN:
                if hr_zones:
                    easy_pace_mid = (pace_zones.easy_low + pace_zones.easy_high) / 2
                    duration_min = round(long_run_km * easy_pace_mid / 60 / 5) * 5
                    w = PlannedWorkout(
                        plan_id=plan_id,
                        week_number=week_number,
                        day_of_week=day,
                        workout_type=wt,
                        target_distance_km=long_run_km,
                        target_duration_minutes=duration_min,
                        target_hr_low=hr_zones.easy_low,
                        target_hr_high=hr_zones.easy_high,
                        phase=phase,
                        description_ja=f"ロングラン {int(duration_min)}分",
                    )
                else:
                    w = PlannedWorkout(
                        plan_id=plan_id,
                        week_number=week_number,
                        day_of_week=day,
                        workout_type=wt,
                        target_distance_km=long_run_km,
                        target_pace_low=pace_zones.easy_low,
                        target_pace_high=pace_zones.easy_high,
                        phase=phase,
                        description_ja=f"ロングラン {long_run_km}km",
                    )
            elif wt == WorkoutType.TEMPO:
                w = PlannedWorkout(
                    plan_id=plan_id,
                    week_number=week_number,
                    day_of_week=day,
                    workout_type=wt,
                    target_distance_km=quality_km[wt],
                    target_pace_low=pace_zones.threshold + 10,  # slightly slower
                    target_pace_high=pace_zones.threshold,
                    phase=phase,
                    warmup_minutes=10.0,
                    cooldown_minutes=10.0,
                    description_ja=f"テンポラン {quality_km[wt]}km",
                )
            elif wt == WorkoutType.THRESHOLD:
                w = PlannedWorkout(
                    plan_id=plan_id,
                    week_number=week_number,
                    day_of_week=day,
                    workout_type=wt,
                    target_distance_km=quality_km[wt],
                    target_pace_low=pace_zones.threshold + 5,
                    target_pace_high=pace_zones.threshold - 5,
                    phase=phase,
                    warmup_minutes=10.0,
                    cooldown_minutes=10.0,
                    description_ja=f"閾値走 {quality_km[wt]}km",
                )
            elif wt == WorkoutType.INTERVAL:
                intervals = IntervalDetail(
                    repetitions=5,
                    work_distance_m=1000,
                    work_pace_low=pace_zones.interval + 5,
                    work_pace_high=pace_zones.interval - 5,
                    recovery_duration_minutes=3.0,
                )
                w = PlannedWorkout(
                    plan_id=plan_id,
                    week_number=week_number,
                    day_of_week=day,
                    workout_type=wt,
                    target_distance_km=quality_km[wt],
                    target_pace_low=pace_zones.interval + 5,
                    target_pace_high=pace_zones.interval - 5,
                    phase=phase,
                    warmup_minutes=10.0,
                    cooldown_minutes=10.0,
                    intervals=intervals,
                    description_ja="インターバル 5x1000m",
                )
            elif wt == WorkoutType.REPETITION:
                intervals = IntervalDetail(
                    repetitions=8,
                    work_distance_m=400,
                    work_pace_low=pace_zones.repetition + 5,
                    work_pace_high=pace_zones.repetition - 5,
                    recovery_duration_minutes=2.0,
                )
                w = PlannedWorkout(
                    plan_id=plan_id,
                    week_number=week_number,
                    day_of_week=day,
                    workout_type=wt,
                    target_distance_km=quality_km[wt],
                    target_pace_low=pace_zones.repetition + 5,
                    target_pace_high=pace_zones.repetition - 5,
                    phase=phase,
                    warmup_minutes=10.0,
                    cooldown_minutes=10.0,
                    intervals=intervals,
                    description_ja="レペティション 8x400m",
                )
            else:
                raise ValueError(f"Unsupported workout type: {wt}")

            workouts.append(w)

        return workouts


def _assign_days(
    runs_per_week: int,
    preferred_long_run_day: int,
    rest_days: list[int] | None = None,
) -> list[int]:
    """Assign day_of_week for each workout slot.

    Distributes runs across the week, with the last slot (long run)
    on the preferred day. Avoids rest_days if specified.

    Args:
        runs_per_week: Number of runs per week (3-6).
        preferred_long_run_day: Day for long run (1=Mon, 7=Sun).
        rest_days: Days to avoid (1=Mon, 7=Sun). E.g., [3] for Wednesday off.

    Returns:
        List of day_of_week values (1=Mon, 7=Sun).
    """
    if rest_days:
        # Build available days excluding rest days and long run day
        all_days = [d for d in range(1, 8) if d not in rest_days]
        if preferred_long_run_day in all_days:
            all_days.remove(preferred_long_run_day)
        # Need runs_per_week - 1 non-long-run days
        needed = runs_per_week - 1
        # Spread evenly across available days
        if len(all_days) >= needed:
            step = len(all_days) / needed
            selected = [all_days[int(i * step)] for i in range(needed)]
        else:
            selected = all_days[:needed]
        selected.append(preferred_long_run_day)
        selected.sort()
        return selected

    patterns = {
        3: [2, 4, 7],  # Tue, Thu, Sun
        4: [1, 3, 5, 7],  # Mon, Wed, Fri, Sun
        5: [1, 2, 4, 5, 7],  # Mon, Tue, Thu, Fri, Sun
        6: [1, 2, 3, 5, 6, 7],  # Mon-Wed, Fri-Sun
    }
    days = list(patterns.get(runs_per_week, patterns[4]))
    days[-1] = preferred_long_run_day
    return days
