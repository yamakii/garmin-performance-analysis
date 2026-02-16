"""Training plan generator - orchestrates all components."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from garmin_mcp.training_plan.activity_matcher import ActivityMatcher
from garmin_mcp.training_plan.fitness_assessor import FitnessAssessor
from garmin_mcp.training_plan.models import (
    FitnessSummary,
    GoalType,
    PeriodizationPhase,
    PlannedWorkout,
    TrainingPlan,
    WorkoutType,
)
from garmin_mcp.training_plan.periodization import PeriodizationEngine
from garmin_mcp.training_plan.vdot import VDOTCalculator
from garmin_mcp.training_plan.weekly_templates import WeeklyTemplateEngine

logger = logging.getLogger(__name__)


class TrainingPlanGenerator:
    """Generates personalized training plans."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self.last_fitness: FitnessSummary | None = None

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
        self.last_fitness = fitness

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
        if goal == GoalType.RETURN_TO_RUN and fitness.gap_detected:
            # Gap-aware: start from recent actual volume, target 75% of pre-gap
            if fitness.recent_runs:
                recent_total = sum(r.get("distance_km", 0) for r in fitness.recent_runs)
                recent_weekly_est = recent_total  # recent 1-2 weeks total
            else:
                recent_weekly_est = fitness.weekly_volume_km
            start_km = max(10.0, recent_weekly_est)

            # Peak: 75% of pre-gap volume (minimum start * 1.1)
            pre_gap_target = fitness.pre_gap_weekly_volume_km * 0.75
            peak_km = max(start_km * 1.1, pre_gap_target)
        else:
            start_km = fitness.weekly_volume_km
            # Conservative 30% increase for return_to_run, 50% for others
            peak_km = (
                start_km * 1.3 if goal == GoalType.RETURN_TO_RUN else start_km * 1.5
            )
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
        # return_to_run: auto-set start_frequency to runs_per_week - 1
        # (e.g. RECOVERY phase at 3 runs/week, BASE phase at 4 runs/week)
        if goal == GoalType.RETURN_TO_RUN and start_frequency is None:
            start_frequency = max(runs_per_week - 1, 3)

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

    def update(self, plan_id: str) -> TrainingPlan:
        """Update existing plan by creating a new version.

        Steps:
        1. Read existing plan (latest active version)
        2. Run ActivityMatcher to find completed workouts
        3. Re-assess fitness
        4. Build new TrainingPlan preserving completed weeks
        5. Regenerate remaining weeks with new fitness
        6. Save with insert_training_plan(previous_version=prev)
        """
        from garmin_mcp.database.readers.training_plans import TrainingPlanReader

        # 1. Read existing plan
        reader = TrainingPlanReader(db_path=self._db_path)
        existing = reader.get_training_plan(plan_id)
        if "error" in existing:
            raise ValueError(f"Plan not found: {existing['error']}")

        prev_version = existing.get("version", 1)
        new_version = prev_version + 1

        # 2. Match activities
        matcher = ActivityMatcher(db_path=self._db_path)
        matches = matcher.match_activities(plan_id, prev_version)
        completed_weeks, last_completed_week = matcher.get_completed_weeks(
            plan_id, prev_version
        )

        # Build match lookup: workout_id -> actual_activity_id
        match_map = {m.workout_id: m.actual_activity_id for m in matches}

        # 3. Re-assess fitness
        assessor = FitnessAssessor(db_path=self._db_path)
        fitness = assessor.assess()
        self.last_fitness = fitness

        vdot = fitness.vdot
        pace_zones = fitness.pace_zones

        # 4. Extract plan parameters from existing
        goal = GoalType(existing["goal_type"])
        total_weeks = existing["total_weeks"]
        start_date = date.fromisoformat(str(existing["start_date"]))
        runs_per_week = existing["runs_per_week"]
        target_race_date_str = existing.get("target_race_date")
        target_race_date = (
            date.fromisoformat(str(target_race_date_str))
            if target_race_date_str
            else None
        )
        target_time_seconds = existing.get("target_time_seconds")

        freq_prog_json = existing.get("frequency_progression_json")
        freq_prog = None
        if freq_prog_json:
            import json

            freq_prog = (
                json.loads(freq_prog_json)
                if isinstance(freq_prog_json, str)
                else freq_prog_json
            )

        # 5. Rebuild phases
        if goal == GoalType.RETURN_TO_RUN:
            phases = PeriodizationEngine.create_return_to_run_phases(total_weeks)
        elif goal == GoalType.FITNESS:
            phases = PeriodizationEngine.create_fitness_phases(total_weeks)
        else:
            phases = PeriodizationEngine.create_race_phases(total_weeks, goal)

        # 6. Volume progression (using new fitness)
        start_km = existing["weekly_volume_start_km"]
        peak_km = existing["weekly_volume_peak_km"]
        weekly_volumes = PeriodizationEngine.weekly_volume_progression(
            start_km, peak_km, phases
        )

        # 7. Build new plan
        plan = TrainingPlan(
            plan_id=plan_id,
            version=new_version,
            goal_type=goal,
            target_race_date=target_race_date,
            target_time_seconds=target_time_seconds,
            vdot=round(vdot, 1),
            pace_zones=pace_zones,
            total_weeks=total_weeks,
            start_date=start_date,
            weekly_volume_start_km=round(start_km, 1),
            weekly_volume_peak_km=round(peak_km, 1),
            runs_per_week=runs_per_week,
            frequency_progression=freq_prog,
            phases=phases,
            weekly_volumes=[round(v, 1) for v in weekly_volumes],
            workouts=[],
            status="active",
        )

        # 8a. Copy completed week workouts (preserving actual_activity_id)
        existing_workouts = existing.get("workouts", [])
        for wo_data in existing_workouts:
            wo_week = wo_data.get("week_number")
            if wo_week in completed_weeks:
                wo = PlannedWorkout(
                    workout_id=wo_data["workout_id"],
                    plan_id=plan_id,
                    version=new_version,
                    week_number=wo_week,
                    day_of_week=wo_data["day_of_week"],
                    workout_date=(
                        date.fromisoformat(str(wo_data["workout_date"]))
                        if wo_data.get("workout_date")
                        else None
                    ),
                    workout_type=WorkoutType(wo_data["workout_type"]),
                    phase=PeriodizationPhase(wo_data["phase"]),
                    target_distance_km=wo_data.get("target_distance_km"),
                    actual_activity_id=match_map.get(wo_data["workout_id"]),
                )
                plan.workouts.append(wo)

        # 8b. Regenerate remaining weeks
        regen_start_week = last_completed_week + 1

        week_offset = 0
        for phase, num_weeks in phases:
            for w in range(num_weeks):
                week_num = week_offset + w + 1
                if week_num > len(weekly_volumes):
                    break
                if week_num < regen_start_week:
                    continue  # Skip completed weeks

                vol = weekly_volumes[week_num - 1]
                week_freq = plan.get_week_frequency(week_num)

                template = WeeklyTemplateEngine.get_weekly_template(
                    week_freq, phase, goal
                )
                workouts = WeeklyTemplateEngine.fill_workout_details(
                    template,
                    week_num,
                    plan_id,
                    phase,
                    vol,
                    pace_zones,
                    preferred_long_run_day=7,
                    hr_zones=fitness.hr_zones,
                )
                for wo in workouts:
                    wo.version = new_version
                    wo.workout_date = start_date + timedelta(
                        weeks=wo.week_number - 1, days=wo.day_of_week - 1
                    )
                plan.workouts.extend(workouts)
            week_offset += num_weeks

        # 9. Cleanup stale Garmin uploads (uploaded but not completed)
        self._cleanup_stale_garmin_workouts(existing_workouts, match_map)

        # 10. Save to DB
        try:
            from garmin_mcp.database.inserters.training_plans import (
                insert_training_plan,
            )

            insert_training_plan(self._db_path, plan, previous_version=prev_version)
        except Exception as e:
            logger.warning(f"Failed to save updated plan to DB: {e}")

        return plan

    def _cleanup_stale_garmin_workouts(
        self,
        existing_workouts: list[dict],
        match_map: dict[str, int],
    ) -> None:
        """Delete stale uploaded workouts from Garmin Connect.

        Stale = garmin_workout_id is set but no actual_activity_id
        (uploaded to Garmin calendar but not yet completed by user).
        These will be replaced by regenerated workouts.
        """
        stale_workout_ids = [
            wo["workout_id"]
            for wo in existing_workouts
            if wo.get("garmin_workout_id") and wo["workout_id"] not in match_map
        ]

        if not stale_workout_ids:
            return

        try:
            from garmin_mcp.training_plan.garmin_uploader import (
                GarminWorkoutUploader,
            )

            uploader = GarminWorkoutUploader(db_path=self._db_path)
            for workout_id in stale_workout_ids:
                try:
                    result = uploader.delete_workout(workout_id)
                    if result.get("error"):
                        logger.warning(
                            f"Failed to cleanup Garmin workout {workout_id}: "
                            f"{result['error']}"
                        )
                except Exception as e:
                    logger.warning(f"Garmin cleanup error for {workout_id}: {e}")
        except Exception as e:
            logger.warning(f"Garmin cleanup skipped: {e}")
