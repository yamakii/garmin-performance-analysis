"""Periodization engine for training plan phase structure and volume progression.

This module handles the macro-level planning of training phases and weekly volume
progression for both race-targeted and general fitness plans.
"""

from garmin_mcp.training_plan.models import GoalType, PeriodizationPhase


class PeriodizationEngine:
    """Engine for creating training phases and calculating volume progression."""

    @staticmethod
    def create_race_phases(
        total_weeks: int, goal_type: GoalType
    ) -> list[tuple[PeriodizationPhase, int]]:
        """Create phase structure for race-targeted plans.

        Phase distribution:
        - 5K/10K: Base 40%, Build 30%, Peak 20%, Taper 10%
        - Half:   Base 35%, Build 30%, Peak 20%, Taper 15%
        - Full:   Base 30%, Build 30%, Peak 25%, Taper 15%

        Minimum 1 week per phase. Rounds to integer weeks.

        Args:
            total_weeks: Total number of weeks in the plan
            goal_type: Type of race goal (5K, 10K, half, full marathon)

        Returns:
            List of (phase, weeks) tuples representing the phase structure
        """
        # Define phase distribution percentages by goal type
        distributions = {
            GoalType.RACE_5K: {
                PeriodizationPhase.BASE: 0.40,
                PeriodizationPhase.BUILD: 0.30,
                PeriodizationPhase.PEAK: 0.20,
                PeriodizationPhase.TAPER: 0.10,
            },
            GoalType.RACE_10K: {
                PeriodizationPhase.BASE: 0.40,
                PeriodizationPhase.BUILD: 0.30,
                PeriodizationPhase.PEAK: 0.20,
                PeriodizationPhase.TAPER: 0.10,
            },
            GoalType.RACE_HALF: {
                PeriodizationPhase.BASE: 0.35,
                PeriodizationPhase.BUILD: 0.30,
                PeriodizationPhase.PEAK: 0.20,
                PeriodizationPhase.TAPER: 0.15,
            },
            GoalType.RACE_FULL: {
                PeriodizationPhase.BASE: 0.30,
                PeriodizationPhase.BUILD: 0.30,
                PeriodizationPhase.PEAK: 0.25,
                PeriodizationPhase.TAPER: 0.15,
            },
        }

        dist = distributions[goal_type]

        # Calculate weeks per phase with minimum 1 week
        base_weeks = max(1, round(total_weeks * dist[PeriodizationPhase.BASE]))
        build_weeks = max(1, round(total_weeks * dist[PeriodizationPhase.BUILD]))
        peak_weeks = max(1, round(total_weeks * dist[PeriodizationPhase.PEAK]))
        taper_weeks = max(1, round(total_weeks * dist[PeriodizationPhase.TAPER]))

        # Adjust to match total_weeks exactly
        allocated = base_weeks + build_weeks + peak_weeks + taper_weeks
        if allocated != total_weeks:
            diff = total_weeks - allocated
            # Add/subtract from base phase (largest phase)
            base_weeks += diff

        return [
            (PeriodizationPhase.BASE, base_weeks),
            (PeriodizationPhase.BUILD, build_weeks),
            (PeriodizationPhase.PEAK, peak_weeks),
            (PeriodizationPhase.TAPER, taper_weeks),
        ]

    @staticmethod
    def create_fitness_phases(total_weeks: int) -> list[tuple[PeriodizationPhase, int]]:
        """Create 4-week mesocycle: 3 build + 1 recovery, repeating.

        Args:
            total_weeks: Total number of weeks in the plan

        Returns:
            List of (phase, weeks) tuples representing mesocycles
        """
        phases = []
        remaining_weeks = total_weeks

        while remaining_weeks > 0:
            if remaining_weeks >= 4:
                # Full mesocycle: 3 build + 1 recovery
                phases.append((PeriodizationPhase.BUILD, 3))
                phases.append((PeriodizationPhase.RECOVERY, 1))
                remaining_weeks -= 4
            else:
                # Partial mesocycle at the end
                if remaining_weeks == 3:
                    phases.append((PeriodizationPhase.BUILD, 3))
                elif remaining_weeks == 2:
                    phases.append((PeriodizationPhase.BUILD, 2))
                else:  # remaining_weeks == 1
                    phases.append((PeriodizationPhase.BUILD, 1))
                remaining_weeks = 0

        return phases

    @staticmethod
    def weekly_volume_progression(
        start_km: float,
        peak_km: float,
        phases: list[tuple[PeriodizationPhase, int]],
    ) -> list[float]:
        """Calculate weekly volume targets.

        Rules:
        - Base/Build: Linear increase from start_km to peak_km, max +10% per week
        - Peak: Maintain peak_km (±5%)
        - Taper: Decrease to 40-60% of peak linearly
        - Recovery: 80% of current week's target
        - Every 4th week in base/build is a recovery week (volume * 0.8)

        Args:
            start_km: Starting weekly volume in kilometers
            peak_km: Peak weekly volume in kilometers
            phases: List of (phase, weeks) tuples

        Returns:
            List of weekly volume targets in kilometers
        """
        weekly_volumes = []
        week_count = 0

        # Count weeks in base and build phases for progression calculation
        base_build_weeks = sum(
            weeks
            for phase, weeks in phases
            if phase in (PeriodizationPhase.BASE, PeriodizationPhase.BUILD)
        )

        # Calculate progression increment respecting 10% rule
        if base_build_weeks > 0:
            total_increase = peak_km - start_km
            weeks_for_increase = base_build_weeks - (
                base_build_weeks // 4
            )  # Subtract recovery weeks
            if weeks_for_increase > 0:
                weekly_increment = total_increase / weeks_for_increase
                max_increment = start_km * 0.10
                weekly_increment = min(weekly_increment, max_increment)
            else:
                weekly_increment = 0
        else:
            weekly_increment = 0

        current_volume = start_km

        for phase, weeks in phases:
            if phase in (PeriodizationPhase.BASE, PeriodizationPhase.BUILD):
                # Build phase with recovery weeks
                for _i in range(weeks):
                    week_count += 1
                    # Every 4th week is recovery
                    if week_count % 4 == 0:
                        weekly_volumes.append(current_volume * 0.8)
                    else:
                        weekly_volumes.append(current_volume)
                        # Increase volume for next week, but don't exceed peak
                        current_volume = min(current_volume + weekly_increment, peak_km)

            elif phase == PeriodizationPhase.PEAK:
                # Maintain peak volume
                for _i in range(weeks):
                    weekly_volumes.append(peak_km)

            elif phase == PeriodizationPhase.TAPER:
                # Linear decrease from current volume to 40-60% of peak
                taper_start = weekly_volumes[-1] if weekly_volumes else peak_km
                taper_end = peak_km * 0.5  # 50% of peak
                decrement = (taper_start - taper_end) / weeks if weeks > 0 else 0

                for i in range(weeks):
                    weekly_volumes.append(taper_start - decrement * i)

            elif phase == PeriodizationPhase.RECOVERY:
                # Recovery week: 80% of previous week
                base_volume = weekly_volumes[-1] if weekly_volumes else start_km
                for _i in range(weeks):
                    weekly_volumes.append(base_volume * 0.8)

        return weekly_volumes
