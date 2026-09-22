"""Pydantic schemas for section analysis data validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    good_points: list[GroundedPoint] = Field(min_length=0, max_length=3)
    growth_points: list[GroundedPoint] = Field(default_factory=list, max_length=2)
    next_challenge: str = Field(min_length=10, max_length=240)
    timeline: list[TimelineItem] = Field(min_length=1, max_length=5)
    notes: list[SignalNote] = Field(default_factory=list, max_length=3)
    question: str | None = Field(default=None, max_length=160)


SECTION_SCHEMAS: dict[str, type[BaseModel]] = {
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
