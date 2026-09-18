"""Pydantic schemas for section analysis data validation."""

from __future__ import annotations

import re
from typing import Any, Literal

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


class PrescriptionVerdict(BaseModel):
    """How the run answered the session prescribed for that day (Issue #984).

    Computed by ``analysis.derivations.compute_prescription_verdict`` and
    transcribed verbatim by the summary agent, so the verdict symbol is typed
    to the three allowed values rather than left as free text.
    """

    verdict: Literal["✅", "🟡", "🔴"]
    prescription_title: str
    reasons: list[str]
    # Axes the run answered as prescribed -- "intensity_class" | "volume" |
    # "hr_ceiling" | "rest" (Issue #1086). The summary agent must not recycle an
    # on-plan axis as an improvement area.
    on_plan: list[str] = Field(default_factory=list)


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
    # Prescription vs actual (Issue #984). Transcribed from the prefetch
    # CONTEXT, so both stay absent on unprescribed days, when no comparable
    # same-type run exists, and in every summary stored before this layer.
    prescription_verdict: PrescriptionVerdict | None = None
    vs_previous: dict[str, Any] | None = None


class GroundedPoint(BaseModel):
    """One coach point plus the key of the datum that supports it (#1251).

    ``evidence`` is resolved against the run report by
    ``validators.check_run_note_grounding``; the pattern only fixes its shape
    (``<prefix>.<key>``), never whether that key actually exists.
    """

    text: str = Field(min_length=8, max_length=160)
    evidence: str = Field(
        pattern=r"^(plan|signals|moments|recurrence|vs_previous|conditions|context)"
        r"\.[a-z0-9_]+$"
    )


class TimelineItem(BaseModel):
    """One scene of the run, keyed by a moment id from the run report."""

    moment_id: str = Field(pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=8, max_length=300)


class SignalNote(BaseModel):
    """A short explanation of one adverse out-of-range signal."""

    signal: str = Field(pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=8, max_length=300)


class RunNoteAnalysisData(BaseModel):
    """Schema for the single coach-review section (Epic #1247, Issue #1251).

    ``run_note`` replaces the five legacy sections: everything a number can
    decide is rendered deterministically, so this section carries only the
    prose a coach adds on top -- meaning, causality, flow, weighting, the next
    step, recurrence and at most one question.
    """

    story: str = Field(min_length=20, max_length=400)
    good_points: list[GroundedPoint] = Field(min_length=1, max_length=3)
    growth_points: list[GroundedPoint] = Field(default_factory=list, max_length=2)
    next_challenge: str = Field(min_length=10, max_length=240)
    timeline: list[TimelineItem] = Field(min_length=1, max_length=5)
    notes: list[SignalNote] = Field(default_factory=list, max_length=3)
    question: str | None = Field(default=None, max_length=160)


SECTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "split": SplitAnalysisData,
    "phase": PhaseAnalysisData,
    "efficiency": EfficiencyAnalysisData,
    "environment": EnvironmentAnalysisData,
    "summary": SummaryAnalysisData,
    "run_note": RunNoteAnalysisData,
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
