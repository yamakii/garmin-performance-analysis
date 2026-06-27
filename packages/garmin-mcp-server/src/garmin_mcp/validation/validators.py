"""Validation functions for ingest pipeline records.

Called by inserters before DuckDB INSERT to catch physically impossible values.
Raises pydantic.ValidationError on invalid data.
"""

from __future__ import annotations

import re

from garmin_mcp.validation.models import ActivityRecord, SplitRecord

# Summary star_rating must look like ``★★★★☆ 4.2/5.0``: 1-5 filled stars,
# 0-4 empty stars, then a ``N.N/5.0`` numeric rating. The captured group is the
# numeric rating, which must additionally fall within [0.0, 5.0].
_STAR_RATING_PATTERN = re.compile(r"^★{1,5}☆{0,4}\s*(\d+(?:\.\d+)?)/5\.0$")

# Skip phrases that indicate "no baseline / data unavailable" narration.
# When form_baseline_trend.success is True (comparison data exists), any of
# these in the efficiency section's form_trend is an inconsistency (the LLM
# wrongly fell back to the success=False skip template). When success is
# False, such phrases are legitimate and allowed.
_FORM_TREND_SKIP_PHRASES: tuple[str, ...] = (
    "省略",
    "含まれていない",
    "含まれておらず",
    "データ不足",
    "ベースラインがない",
    "ベースラインが存在しない",
    "比較できません",
    "蓄積されれば",
)


def check_form_trend_consistency(
    form_trend_text: str,
    baseline_success: bool,
) -> tuple[bool, list[str]]:
    """Check efficiency ``form_trend`` text against baseline availability.

    Deterministic guard for the non-deterministic LLM narration bug where the
    efficiency section emits a "no baseline / omitted" skip sentence even
    though ``form_baseline_trend.success`` is True (comparison data exists).

    Args:
        form_trend_text: The efficiency section's ``form_trend`` field text.
        baseline_success: ``form_baseline_trend["success"]`` from the reader,
            i.e. whether a 1-month comparison is actually available.

    Returns:
        ``(True, [])`` when consistent. ``(False, [error, ...])`` when
        ``baseline_success`` is True but the text is empty or contains a skip
        phrase (an inconsistency that must not be inserted). When
        ``baseline_success`` is False, skip phrases are legitimate and the
        result is always ``(True, [])``.
    """
    if not baseline_success:
        # success=False: skip narration (or empty) is legitimate.
        return True, []

    text = form_trend_text or ""
    stripped = text.strip()
    if not stripped:
        return (
            False,
            [
                "form_trend is empty but form_baseline_trend.success=True "
                "(a 1-month comparison is available)"
            ],
        )

    matched = [phrase for phrase in _FORM_TREND_SKIP_PHRASES if phrase in text]
    if matched:
        return (
            False,
            [
                "form_trend contains skip phrase(s) "
                f"{matched} but form_baseline_trend.success=True "
                "(a 1-month comparison is available)"
            ],
        )

    return True, []


def check_narration_numeric_consistency(
    analysis_data: dict,
) -> tuple[bool, list[str]]:
    """Deterministically validate the summary section's structured numbers.

    Guard for the non-deterministic LLM narration bug where the summary section
    emits out-of-range structured values (``integrated_score=120``,
    ``★★★★★ 6.5/5.0``, a malformed star rating). Such records must not be
    inserted into DuckDB.

    Validates:
        - ``integrated_score`` ∈ [0.0, 100.0]
        - ``star_rating`` matches ``★{1,5}☆{0,4} N.N/5.0`` and the extracted
          numeric rating ∈ [0.0, 5.0]

    Args:
        analysis_data: The summary section's ``analysis_data`` dict.

    Returns:
        ``(True, [])`` when consistent (or when the target fields are absent —
        absence is left to existing schema validation). ``(False, [error, ...])``
        when a present field is out of range or malformed.
    """
    errors: list[str] = []

    score = analysis_data.get("integrated_score")
    if score is not None:
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            errors.append(f"integrated_score is not numeric: {score!r}")
        else:
            if not (0.0 <= score_val <= 100.0):
                errors.append(
                    f"integrated_score={score_val} is out of range [0.0, 100.0]"
                )

    star_rating = analysis_data.get("star_rating")
    if star_rating is not None:
        match = _STAR_RATING_PATTERN.match(str(star_rating).strip())
        if not match:
            errors.append(
                f"star_rating {star_rating!r} does not match the expected "
                "format '★{1,5}☆{0,4} N.N/5.0'"
            )
        else:
            rating_val = float(match.group(1))
            if not (0.0 <= rating_val <= 5.0):
                errors.append(
                    f"star_rating numeric value {rating_val} is out of "
                    "range [0.0, 5.0]"
                )

    return (not errors), errors


def validate_activity(data: dict) -> ActivityRecord:
    """Validate activity data dict and return ActivityRecord.

    Args:
        data: Dict with activity fields matching ActivityRecord schema.

    Returns:
        Validated ActivityRecord instance.

    Raises:
        pydantic.ValidationError: If any field violates physical constraints.
    """
    return ActivityRecord.model_validate(data)


def validate_split(data: dict) -> SplitRecord:
    """Validate a single split data dict and return SplitRecord.

    Args:
        data: Dict with split fields matching SplitRecord schema.

    Returns:
        Validated SplitRecord instance.

    Raises:
        pydantic.ValidationError: If any field violates physical constraints.
    """
    return SplitRecord.model_validate(data)


def validate_splits(activity_id: int, splits: list[dict]) -> list[SplitRecord]:
    """Validate all split data dicts for an activity.

    Args:
        activity_id: Activity ID (injected into each split dict).
        splits: List of split data dicts.

    Returns:
        List of validated SplitRecord instances.

    Raises:
        pydantic.ValidationError: On first invalid record.
    """
    records = []
    for split in splits:
        split_data = {**split, "activity_id": activity_id}
        records.append(SplitRecord.model_validate(split_data))
    return records
