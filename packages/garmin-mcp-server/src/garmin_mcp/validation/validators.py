"""Validation functions for ingest pipeline records.

Called by inserters before DuckDB INSERT to catch physically impossible values.
Raises pydantic.ValidationError on invalid data.
"""

from __future__ import annotations

from garmin_mcp.validation.models import ActivityRecord, SplitRecord

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
