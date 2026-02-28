"""Pydantic schemas for section analysis data validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SplitAnalysisData(BaseModel):
    """Schema for split section analysis data."""

    highlights: str = Field(min_length=10, max_length=500)
    analyses: dict[str, str]

    @field_validator("analyses")
    @classmethod
    def validate_analyses_keys(cls, v: dict[str, str]) -> dict[str, str]:
        """Keys must be split_N format."""
        if not v:
            raise ValueError("analyses must not be empty")
        for key in v:
            if not re.match(r"^split_\d+$", key):
                raise ValueError(f"Invalid key format: '{key}'. Must be 'split_N'")
        return v


class PhaseAnalysisData(BaseModel):
    """Schema for phase section analysis data."""

    warmup_evaluation: str = Field(min_length=10)
    run_evaluation: str = Field(min_length=10)
    cooldown_evaluation: str = Field(min_length=10)
    recovery_evaluation: str | None = None
    evaluation_criteria: str = Field(min_length=5)


class EfficiencyAnalysisData(BaseModel):
    """Schema for efficiency section analysis data."""

    efficiency: str = Field(min_length=20)
    evaluation: str = Field(min_length=20)
    form_trend: str = Field(min_length=10)


class EnvironmentAnalysisData(BaseModel):
    """Schema for environment section analysis data."""

    environmental: str = Field(min_length=20)


class NextRunTarget(BaseModel):
    """Flexible model - fields vary by training type."""

    model_config = {"extra": "allow"}

    recommended_type: str | None = None
    summary_ja: str | None = None
    insufficient_data: bool | None = None


class PlanAchievement(BaseModel):
    """Schema for plan achievement data."""

    workout_type: str
    description_ja: str
    targets: dict[str, str]
    actuals: dict[str, str]
    hr_achieved: bool
    pace_achieved: bool
    evaluation: str


class SummaryAnalysisData(BaseModel):
    """Schema for summary section analysis data."""

    star_rating: str
    integrated_score: float | None = Field(default=None, ge=0, le=100)
    summary: str = Field(min_length=10)
    key_strengths: list[str] = Field(min_length=1)
    improvement_areas: list[str]
    next_action: str = Field(min_length=10)
    next_run_target: NextRunTarget | dict[str, Any]
    recommendations: str = Field(min_length=5)
    plan_achievement: PlanAchievement | None = None


SECTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "split": SplitAnalysisData,
    "phase": PhaseAnalysisData,
    "efficiency": EfficiencyAnalysisData,
    "environment": EnvironmentAnalysisData,
    "summary": SummaryAnalysisData,
}

VALID_SECTION_TYPES = set(SECTION_SCHEMAS.keys())


def validate_section_data(
    section_type: str, analysis_data: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Validate analysis_data against section-specific schema.

    Returns (valid, errors).
    """
    if section_type not in SECTION_SCHEMAS:
        return False, [
            f"Unknown section_type: {section_type}. "
            f"Valid types: {sorted(VALID_SECTION_TYPES)}"
        ]

    schema_cls = SECTION_SCHEMAS[section_type]
    try:
        schema_cls.model_validate(analysis_data)
        return True, []
    except Exception as e:
        errors: list[str] = []
        if hasattr(e, "errors"):
            for err in e.errors():  # type: ignore[union-attr]
                loc = " -> ".join(str(x) for x in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
        else:
            errors.append(str(e))
        return False, errors
