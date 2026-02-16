"""Pydantic models for training plan generation."""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GoalType(StrEnum):
    """Training goal type."""

    RACE_5K = "race_5k"
    RACE_10K = "race_10k"
    RACE_HALF = "race_half"
    RACE_FULL = "race_full"
    FITNESS = "fitness"
    RETURN_TO_RUN = "return_to_run"


class PeriodizationPhase(StrEnum):
    """Periodization phase."""

    BASE = "base"
    BUILD = "build"
    PEAK = "peak"
    TAPER = "taper"
    RECOVERY = "recovery"


class WorkoutType(StrEnum):
    """Workout type."""

    EASY = "easy"
    RECOVERY = "recovery"
    TEMPO = "tempo"
    THRESHOLD = "threshold"
    INTERVAL = "interval"
    REPETITION = "repetition"
    LONG_RUN = "long_run"
    RACE_PACE = "race_pace"
    REST = "rest"


class PaceZones(BaseModel):
    """Daniels pace zones in seconds per km."""

    easy_low: float = Field(description="Easy pace low end (sec/km)")
    easy_high: float = Field(description="Easy pace high end (sec/km)")
    marathon: float = Field(description="Marathon pace (sec/km)")
    threshold: float = Field(description="Threshold/tempo pace (sec/km)")
    interval: float = Field(description="Interval pace (sec/km)")
    repetition: float = Field(description="Repetition pace (sec/km)")

    @field_validator(
        "easy_low", "easy_high", "marathon", "threshold", "interval", "repetition"
    )
    @classmethod
    def positive_pace(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Pace must be positive")
        return v


class HRZones(BaseModel):
    """Heart rate zones derived from lactate threshold."""

    easy_low: int = Field(description="Easy HR low (bpm)")
    easy_high: int = Field(description="Easy HR high (bpm)")
    marathon_low: int = Field(description="Marathon HR low (bpm)")
    marathon_high: int = Field(description="Marathon HR high (bpm)")
    threshold_low: int = Field(description="Threshold HR low (bpm)")
    threshold_high: int = Field(description="Threshold HR high (bpm)")


class FitnessSummary(BaseModel):
    """Current fitness assessment."""

    vdot: float = Field(description="Current VDOT value")
    pace_zones: PaceZones
    hr_zones: HRZones | None = None
    weekly_volume_km: float = Field(description="Average weekly volume (km)")
    runs_per_week: float = Field(description="Average runs per week")
    training_type_distribution: dict[str, float] = Field(
        default_factory=dict,
        description="Distribution of training types (e.g., {'easy': 0.6, 'tempo': 0.2})",
    )
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    gap_detected: bool = Field(
        default=False, description="Whether a training gap (7+ days) was detected"
    )
    gap_weeks: int = Field(
        default=0, description="Duration of the longest gap in weeks"
    )
    pre_gap_weekly_volume_km: float = Field(
        default=0, description="Weekly volume before the gap (km)"
    )
    pre_gap_vdot: float | None = Field(
        default=None, description="VDOT estimate before the gap"
    )
    recent_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Post-gap run summaries (date, distance_km, pace)",
    )


class IntervalDetail(BaseModel):
    """Interval workout detail."""

    repetitions: int = Field(ge=1)
    work_distance_m: int | None = None
    work_duration_minutes: float | None = None
    work_pace_low: float | None = Field(
        default=None, description="Work pace low (sec/km)"
    )
    work_pace_high: float | None = Field(
        default=None, description="Work pace high (sec/km)"
    )
    recovery_duration_minutes: float = Field(description="Recovery jog duration (min)")
    recovery_type: str = Field(default="jog", description="Recovery type: jog or walk")


class PlannedWorkout(BaseModel):
    """Individual planned workout."""

    workout_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    plan_id: str
    week_number: int = Field(ge=1)
    day_of_week: int = Field(ge=1, le=7, description="1=Mon, 7=Sun")
    workout_date: date | None = None
    workout_type: WorkoutType
    description_ja: str | None = None
    target_distance_km: float | None = None
    target_duration_minutes: float | None = None
    target_pace_low: float | None = Field(
        default=None, description="Target pace slow end (sec/km)"
    )
    target_pace_high: float | None = Field(
        default=None, description="Target pace fast end (sec/km)"
    )
    target_hr_low: int | None = None
    target_hr_high: int | None = None
    intervals: IntervalDetail | None = None
    phase: PeriodizationPhase
    warmup_minutes: float | None = None
    cooldown_minutes: float | None = None
    garmin_workout_id: int | None = None
    uploaded_at: str | None = None
    actual_activity_id: int | None = None
    adherence_score: float | None = None
    completed_at: str | None = None


class TrainingPlan(BaseModel):
    """Complete training plan."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal_type: GoalType
    target_race_date: date | None = None
    target_time_seconds: int | None = None
    vdot: float
    pace_zones: PaceZones
    total_weeks: int = Field(ge=4, le=24)
    start_date: date
    weekly_volume_start_km: float = Field(gt=0)
    weekly_volume_peak_km: float = Field(gt=0)
    runs_per_week: int = Field(ge=3, le=6)
    frequency_progression: list[int] | None = Field(
        default=None,
        description="Per-week run frequency. Length must match total_weeks. Each value 3-6.",
    )
    phases: list[tuple[PeriodizationPhase, int]] = Field(
        description="List of (phase, weeks) tuples"
    )
    weekly_volumes: list[float] = Field(description="Weekly volume targets in km")
    workouts: list[PlannedWorkout] = Field(default_factory=list)
    personalization_notes: str | None = None
    status: str = Field(default="active")
    created_at: str | None = None

    def get_week_frequency(self, week_number: int) -> int:
        """Get runs-per-week for a specific week.

        Uses frequency_progression if set, otherwise falls back to runs_per_week.
        """
        if self.frequency_progression and 1 <= week_number <= len(
            self.frequency_progression
        ):
            return self.frequency_progression[week_number - 1]
        return self.runs_per_week

    def get_week_workouts(self, week_number: int) -> list[PlannedWorkout]:
        """Get workouts for a specific week."""
        return [w for w in self.workouts if w.week_number == week_number]

    def get_phase_for_week(self, week_number: int) -> PeriodizationPhase | None:
        """Get the phase for a specific week number."""
        current_week = 0
        for phase, weeks in self.phases:
            current_week += weeks
            if week_number <= current_week:
                return phase
        return None

    def to_summary(self) -> dict[str, Any]:
        """Return a summary without individual workouts."""
        return {
            "plan_id": self.plan_id,
            "goal_type": self.goal_type.value,
            "target_race_date": (
                str(self.target_race_date) if self.target_race_date else None
            ),
            "target_time_seconds": self.target_time_seconds,
            "vdot": self.vdot,
            "total_weeks": self.total_weeks,
            "start_date": str(self.start_date),
            "runs_per_week": self.runs_per_week,
            "frequency_progression": self.frequency_progression,
            "weekly_volume_start_km": self.weekly_volume_start_km,
            "weekly_volume_peak_km": self.weekly_volume_peak_km,
            "phases": [(p.value, w) for p, w in self.phases],
            "total_workouts": len(self.workouts),
            "status": self.status,
        }
