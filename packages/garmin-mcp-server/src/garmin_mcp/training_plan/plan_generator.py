"""Training plan generator - orchestrates all components."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor
from garmin_mcp.training_plan.models import (
    GoalType,
    TrainingPlan,
)
from garmin_mcp.training_plan.periodization import PeriodizationEngine
from garmin_mcp.training_plan.vdot import VDOTCalculator
from garmin_mcp.training_plan.weekly_templates import WeeklyTemplateEngine

logger = logging.getLogger(__name__)


class TrainingPlanGenerator:
    """Generates personalized training plans."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def generate(
        self,
        goal_type: str,
        total_weeks: int,
        target_race_date: str | None = None,
        target_time_seconds: int | None = None,
        runs_per_week: int = 4,
        start_frequency: int | None = None,
        preferred_long_run_day: int = 7,
        rest_days: list[int] | None = None,
    ) -> TrainingPlan:
        """Generate a complete training plan.

        Steps:
        1. Assess current fitness (FitnessAssessor)
        2. Determine VDOT and pace zones
        3. Create phase structure (PeriodizationEngine)
        4. Calculate volume progression
        5. Fill weekly workouts (WeeklyTemplateEngine)
        6. Save plan to DB (inserter)
        7. Return TrainingPlan
        """
        # 1. Assess fitness
        assessor = FitnessAssessor(db_path=self._db_path)
        fitness = assessor.assess()

        # 2. Use fitness VDOT and pace zones
        goal = GoalType(goal_type)
        vdot = fitness.vdot
        pace_zones = fitness.pace_zones

        # If target time given, recalculate VDOT from target
        if target_time_seconds and goal not in (
            GoalType.FITNESS,
            GoalType.RETURN_TO_RUN,
        ):
            distances = {
                GoalType.RACE_5K: 5.0,
                GoalType.RACE_10K: 10.0,
                GoalType.RACE_HALF: 21.0975,
                GoalType.RACE_FULL: 42.195,
            }
            if goal in distances:
                target_vdot = VDOTCalculator.vdot_from_race(
                    distances[goal], target_time_seconds
                )
                # Use higher of current and target VDOT for training
                vdot = max(fitness.vdot, target_vdot)
                pace_zones = VDOTCalculator.pace_zones(vdot)

        # 3. Create phases
        if goal == GoalType.RETURN_TO_RUN:
            phases = PeriodizationEngine.create_return_to_run_phases(total_weeks)
        elif goal == GoalType.FITNESS:
            phases = PeriodizationEngine.create_fitness_phases(total_weeks)
        else:
            phases = PeriodizationEngine.create_race_phases(total_weeks, goal)

        # 4. Volume progression
        start_km = fitness.weekly_volume_km
        # Conservative 30% increase for return_to_run, 50% for others
        peak_km = start_km * 1.3 if goal == GoalType.RETURN_TO_RUN else start_km * 1.5
        # Ensure minimum values
        if start_km < 15:
            start_km = 15.0
        if peak_km < start_km * 1.3:
            peak_km = (
                start_km * 1.3 if goal == GoalType.RETURN_TO_RUN else start_km * 1.5
            )

        weekly_volumes = PeriodizationEngine.weekly_volume_progression(
            start_km, peak_km, phases
        )

        # 5. Calculate start date
        if target_race_date:
            race_date = date.fromisoformat(target_race_date)
            start = race_date - timedelta(weeks=total_weeks)
        else:
            # Start next Monday
            today = date.today()
            days_until_monday = (7 - today.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            start = today + timedelta(days=days_until_monday)

        # 6. Frequency progression
        freq_prog = None
        if start_frequency is not None and start_frequency != runs_per_week:
            freq_prog = PeriodizationEngine.frequency_progression(
                start_frequency, runs_per_week, total_weeks
            )

        # 7. Build plan
        plan = TrainingPlan(
            goal_type=goal,
            target_race_date=(
                date.fromisoformat(target_race_date) if target_race_date else None
            ),
            target_time_seconds=target_time_seconds,
            vdot=round(vdot, 1),
            pace_zones=pace_zones,
            total_weeks=total_weeks,
            start_date=start,
            weekly_volume_start_km=round(start_km, 1),
            weekly_volume_peak_km=round(peak_km, 1),
            runs_per_week=runs_per_week,
            frequency_progression=freq_prog,
            phases=phases,
            weekly_volumes=[round(v, 1) for v in weekly_volumes],
            workouts=[],
        )

        # 8. Fill workouts for each week
        week_offset = 0
        for phase, num_weeks in phases:
            for w in range(num_weeks):
                week_num = week_offset + w + 1
                if week_num > len(weekly_volumes):
                    break
                vol = weekly_volumes[week_num - 1]
                week_freq = plan.get_week_frequency(week_num)

                template = WeeklyTemplateEngine.get_weekly_template(
                    week_freq, phase, goal
                )
                workouts = WeeklyTemplateEngine.fill_workout_details(
                    template,
                    week_num,
                    plan.plan_id,
                    phase,
                    vol,
                    pace_zones,
                    preferred_long_run_day,
                    hr_zones=fitness.hr_zones,
                    rest_days=rest_days,
                )
                # Assign workout_date based on start_date + week/day
                for wo in workouts:
                    wo.workout_date = start + timedelta(
                        weeks=wo.week_number - 1, days=wo.day_of_week - 1
                    )
                plan.workouts.extend(workouts)
            week_offset += num_weeks

        # 9. Save to DB
        try:
            from garmin_mcp.database.inserters.training_plans import (
                insert_training_plan,
            )

            insert_training_plan(self._db_path, plan)
        except Exception as e:
            logger.warning(f"Failed to save plan to DB: {e}")

        return plan
