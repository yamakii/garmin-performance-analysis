"""Validation functions for ingest pipeline records.

Called by inserters before DuckDB INSERT to catch physically impossible values.
Raises pydantic.ValidationError on invalid data.
"""

from __future__ import annotations

import re
from typing import Any

from garmin_mcp.analysis.derivations import compute_weighted_star_rating
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


# Sections whose star_rating is a weighted average the guard can recompute.
_WEIGHTED_STAR_SECTIONS = frozenset({"summary", "phase", "environment"})

# Max tolerated |recomputed - stated| difference. round(x, 1) on both sides
# means anything beyond one decimal place of drift is an LLM arithmetic error.
_STAR_WEIGHTING_TOLERANCE = 0.05


def check_star_weighting_consistency(
    section_type: str, analysis_data: dict[str, Any]
) -> tuple[bool, str | None]:
    """Verify the stated star_rating against its weighted-axis breakdown.

    Deterministic guard for the LLM-computed weighted star ratings (summary
    4-axis, phase, environment; Issue #706). When ``analysis_data`` carries a
    ``star_rating_breakdown`` object::

        {"axis_scores": {...}, "weights": {...}, "star_rating": 3.7}

    the rating is recomputed with
    :func:`garmin_mcp.analysis.derivations.compute_weighted_star_rating` and
    compared against the stated value. The stated value is the breakdown's
    numeric ``star_rating`` when present, otherwise the numeric part of the
    top-level ``star_rating`` string (``★★★★☆ 3.7/5.0``).

    Args:
        section_type: The section type of the analysis JSON.
        analysis_data: The section's ``analysis_data`` dict.

    Returns:
        ``(True, None)`` when consistent, or when the check does not apply:
        section types without weighted ratings, or JSON without axis scores /
        weights / a stated rating (agents not yet emitting the breakdown).
        ``(False, reason)`` when the breakdown is malformed or the recomputed
        rating differs from the stated one by more than 0.05.
    """
    if section_type not in _WEIGHTED_STAR_SECTIONS:
        return True, None

    breakdown = analysis_data.get("star_rating_breakdown")
    if not isinstance(breakdown, dict):
        return True, None
    axis_scores = breakdown.get("axis_scores")
    weights = breakdown.get("weights")
    if not isinstance(axis_scores, dict) or not isinstance(weights, dict):
        return True, None

    stated: float | None = None
    breakdown_rating = breakdown.get("star_rating")
    if isinstance(breakdown_rating, int | float):
        stated = float(breakdown_rating)
    else:
        match = _STAR_RATING_PATTERN.match(str(analysis_data.get("star_rating", "")))
        if match:
            stated = float(match.group(1))
    if stated is None:
        return True, None

    try:
        recomputed = compute_weighted_star_rating(axis_scores, weights)
    except (TypeError, ValueError) as e:
        return False, f"star_rating_breakdown is malformed: {e}"

    if abs(recomputed - stated) > _STAR_WEIGHTING_TOLERANCE:
        return False, (
            f"star_rating {stated} does not match the weighted recomputation "
            f"{recomputed} from star_rating_breakdown "
            f"(axis_scores={axis_scores}, weights={weights})"
        )
    return True, None


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
