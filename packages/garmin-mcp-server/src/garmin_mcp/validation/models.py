"""Pydantic validation models for ingest pipeline records.

Physical constraint ranges reject only values that are physically impossible.
Optional fields accept None (Garmin API frequently omits metrics).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActivityRecord(BaseModel):
    """Validated activity record for DuckDB insertion."""

    activity_id: int
    activity_date: str
    activity_name: str | None = None
    total_distance_km: float | None = Field(default=None, ge=0)
    total_time_seconds: int | None = Field(default=None, ge=0)
    avg_speed_ms: float | None = Field(default=None, ge=0)
    avg_pace_seconds_per_km: float | None = Field(default=None, ge=60, le=1200)
    avg_heart_rate: int | None = Field(default=None, ge=30, le=250)
    max_heart_rate: int | None = Field(default=None, ge=30, le=250)
    temp_celsius: float | None = None
    relative_humidity_percent: float | None = Field(default=None, ge=0, le=100)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    wind_direction: str | None = None
    gear_type: str | None = None
    gear_model: str | None = None
    base_weight_kg: float | None = Field(default=None, ge=0)


class SplitRecord(BaseModel):
    """Validated split record for DuckDB insertion."""

    activity_id: int
    split_index: int = Field(ge=0)
    distance: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    pace_seconds_per_km: float | None = Field(default=None, ge=60, le=1200)
    heart_rate: int | None = Field(default=None, ge=30, le=250)
    cadence: float | None = Field(default=None, ge=100, le=250)
    ground_contact_time: float | None = Field(default=None, ge=100, le=500)
    vertical_oscillation: float | None = Field(default=None, ge=0, le=30)
    vertical_ratio: float | None = Field(default=None, ge=0, le=30)
    elevation_gain: float | None = Field(default=None, ge=0)
    elevation_loss: float | None = Field(default=None, ge=0)
    power: float | None = Field(default=None, ge=0)
    stride_length: float | None = Field(default=None, ge=0)
    max_heart_rate: int | None = Field(default=None, ge=30, le=250)
    max_cadence: float | None = Field(default=None, ge=0)
    max_power: float | None = Field(default=None, ge=0)
    normalized_power: float | None = Field(default=None, ge=0)
    average_speed: float | None = Field(default=None, ge=0)
    grade_adjusted_speed: float | None = Field(default=None, ge=0)
