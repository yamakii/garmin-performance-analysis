"""Plan-independent fitness models: pace/HR zones and fitness summary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


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
    """Heart rate zones from Garmin user settings (5 zones)."""

    zone1_low: int = Field(description="Zone 1 low boundary (bpm)")
    zone1_high: int = Field(description="Zone 1 high boundary (bpm)")
    zone2_low: int = Field(description="Zone 2 low boundary (bpm)")
    zone2_high: int = Field(description="Zone 2 high boundary (bpm)")
    zone3_low: int = Field(description="Zone 3 low boundary (bpm)")
    zone3_high: int = Field(description="Zone 3 high boundary (bpm)")
    zone4_low: int = Field(description="Zone 4 low boundary (bpm)")
    zone4_high: int = Field(description="Zone 4 high boundary (bpm)")
    zone5_low: int = Field(description="Zone 5 low boundary (bpm)")
    zone5_high: int = Field(description="Zone 5 high boundary (bpm)")


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
