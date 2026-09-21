"""Validation functions for ingest pipeline records.

Called by inserters before DuckDB INSERT to catch physically impossible values.
Raises pydantic.ValidationError on invalid data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from garmin_mcp.validation.models import ActivityRecord, SplitRecord

# ---------------------------------------------------------------------------
# run_note grounding (Epic #1247, Issue #1251)
# ---------------------------------------------------------------------------

# ``context.<field>`` is the one evidence prefix that does not resolve against
# the run report, because the prefetch CONTEXT is not part of it. The allowed
# fields are therefore fixed here rather than looked up, so an agent cannot
# invent a context key to justify a claim.
CONTEXT_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "week_position",
        "ladder_step",
        "prescription",
        "morning_wellness",
        "gear",
        "similar_workouts",
    }
)

# (min, max) item counts for the run_note lists, mirroring the schema caps so
# the merge-time guard rejects an over-long list even when the payload reaches
# it without passing through the Pydantic model.
_RUN_NOTE_LIST_CAPS: dict[str, tuple[int, int]] = {
    "good_points": (1, 3),
    "growth_points": (0, 2),
    "timeline": (1, 5),
    "notes": (0, 3),
}

# A signal only carries weight as a weakness when it left its normal range in
# the direction that hurts; ``edge`` and ``within`` are normal, and an outside
# but favourable signal is a strength, never a growth point.
_SIGNAL_OUTSIDE_STATUS = "outside"


def _is_adverse_outlier(signal: Mapping[str, Any]) -> bool:
    """True when a signal is both outside its normal range and adverse."""
    return (
        signal.get("status") == _SIGNAL_OUTSIDE_STATUS and signal.get("adverse") is True
    )


def _index_by(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    """Index a report list (signals / moments / recurrence) by one field."""
    indexed: dict[str, Mapping[str, Any]] = {}
    if not isinstance(items, list):
        return indexed
    for item in items:
        if isinstance(item, Mapping) and item.get(key) is not None:
            indexed[str(item[key])] = item
    return indexed


def _plan_checks(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    """Plan checks indexed by axis, or ``None`` when the run had no plan."""
    plan = report.get("plan")
    if not isinstance(plan, Mapping):
        return None
    return _index_by(plan.get("checks"), "axis")


def _evidence_error(
    evidence: Any,
    report: Mapping[str, Any],
    signals: Mapping[str, Mapping[str, Any]],
    moments: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Any]] | None,
) -> str | None:
    """Return why ``evidence`` does not resolve, or ``None`` when it does."""
    if not isinstance(evidence, str) or "." not in evidence:
        return f"evidence {evidence!r} is not a '<source>.<key>' reference"

    prefix, key = evidence.split(".", 1)

    if prefix == "signals":
        if key not in signals:
            return f"evidence '{evidence}' names a signal the report does not carry"
        return None
    if prefix == "moments":
        if key not in moments:
            return f"evidence '{evidence}' names a moment the report does not carry"
        return None
    if prefix == "recurrence":
        if key not in _index_by(report.get("recurrence"), "kind"):
            return f"evidence '{evidence}' names a recurrence the report does not carry"
        return None
    if prefix == "plan":
        if checks is None:
            return f"evidence '{evidence}' cites a plan but this run had none"
        if key not in checks:
            return f"evidence '{evidence}' names a plan axis the report does not check"
        return None
    if prefix == "vs_previous":
        previous = report.get("vs_previous")
        if not isinstance(previous, Mapping):
            return (
                f"evidence '{evidence}' cites a previous run but the report "
                "carries no comparison"
            )
        if key not in previous:
            return f"evidence '{evidence}' names a vs_previous field that is absent"
        return None
    if prefix == "conditions":
        conditions = report.get("conditions")
        if not isinstance(conditions, Mapping) or key not in conditions:
            return f"evidence '{evidence}' names a conditions field that is absent"
        return None
    if prefix == "context":
        if key not in CONTEXT_EVIDENCE_KEYS:
            return (
                f"evidence '{evidence}' is not one of the allowed context keys "
                f"{sorted(CONTEXT_EVIDENCE_KEYS)}"
            )
        return None

    return f"evidence '{evidence}' uses an unknown source '{prefix}'"


def _growth_point_error(
    evidence: str,
    signals: Mapping[str, Mapping[str, Any]],
    checks: Mapping[str, Mapping[str, Any]] | None,
) -> str | None:
    """Reject a growth point built on a normal signal or an on-plan axis.

    ``evidence`` has already been resolved by :func:`_evidence_error`, so the
    referenced signal / check is known to exist.
    """
    prefix, key = evidence.split(".", 1)

    if prefix == "signals":
        signal = signals[key]
        if not _is_adverse_outlier(signal):
            return (
                f"growth point evidence '{evidence}' rests on a signal with "
                f"status={signal.get('status')!r} adverse={signal.get('adverse')!r}; "
                "only a signal that is outside its normal range AND adverse can "
                "be a growth point"
            )
    elif prefix == "plan" and checks is not None:
        if checks[key].get("on_plan") is True:
            return (
                f"growth point evidence '{evidence}' names a plan axis that came "
                "out on plan; an on-plan axis is never an improvement area"
            )
    return None


def check_run_note_grounding(
    analysis_data: Mapping[str, Any], report: Mapping[str, Any]
) -> tuple[bool, str | None]:
    """Verify every run_note claim against the deterministic run report.

    The coach review (Epic #1247) is the only LLM-written part of the single-run
    page, so nothing in it may float free of the report the page renders. This
    pure guard -- data in, ``(ok, reason)`` out -- rejects a section when:

    1. an ``evidence`` key does not resolve (``plan.<axis>`` /
       ``signals.<metric>`` / ``moments.<id>`` / ``recurrence.<kind>`` /
       ``vs_previous.<field>`` / ``conditions.<field>`` against the report, and
       ``context.<field>`` against :data:`CONTEXT_EVIDENCE_KEYS`);
    2. a growth point rests on a signal that is not both ``outside`` and
       ``adverse`` (a within-range or favourable value is not a weakness);
    3. a growth point names a plan axis that came out ``on_plan``;
    4. a ``timeline`` item names an unknown moment, or there are more timeline
       items than the report has moments (an invented scene);
    5. a note explains a signal that is not an adverse outlier, or an adverse
       outlier is left without a note;
    6. a list exceeds (or falls short of) its documented item count.

    Args:
        analysis_data: The run_note section's ``analysis_data`` mapping.
        report: The deterministic run report the page renders.

    Returns:
        ``(True, None)`` when every claim is grounded, else ``(False, reason)``
        where ``reason`` names the offending key.
    """
    for field, (low, high) in _RUN_NOTE_LIST_CAPS.items():
        items = analysis_data.get(field) or []
        if not isinstance(items, list):
            return False, f"{field} must be a list, got {type(items).__name__}"
        if not low <= len(items) <= high:
            return False, (
                f"{field} carries {len(items)} items, outside the allowed "
                f"{low}-{high}"
            )

    signals = _index_by(report.get("signals"), "metric")
    moments = _index_by(report.get("moments"), "id")
    checks = _plan_checks(report)

    for field in ("good_points", "growth_points"):
        for item in analysis_data.get(field) or []:
            if not isinstance(item, Mapping):
                return False, f"{field} items must be objects, got {item!r}"
            evidence = item.get("evidence")
            error = _evidence_error(evidence, report, signals, moments, checks)
            if error:
                return False, f"{field}: {error}"
            if field == "growth_points":
                error = _growth_point_error(str(evidence), signals, checks)
                if error:
                    return False, error

    timeline = analysis_data.get("timeline") or []
    if len(timeline) > len(moments):
        return False, (
            f"timeline carries {len(timeline)} items but the report has "
            f"{len(moments)} moments (a scene was invented)"
        )
    for item in timeline:
        if not isinstance(item, Mapping):
            return False, f"timeline items must be objects, got {item!r}"
        moment_id = item.get("moment_id")
        if str(moment_id) not in moments:
            return False, (
                f"timeline moment_id '{moment_id}' is not a moment of this run"
            )

    noted: set[str] = set()
    for note in analysis_data.get("notes") or []:
        if not isinstance(note, Mapping):
            return False, f"notes items must be objects, got {note!r}"
        name = str(note.get("signal"))
        signal = signals.get(name)
        if signal is None:
            return False, f"note signal '{name}' is not a signal of this run"
        if not _is_adverse_outlier(signal):
            return False, (
                f"note signal '{name}' has status={signal.get('status')!r} "
                f"adverse={signal.get('adverse')!r}; notes exist only for signals "
                "that are outside their normal range and adverse"
            )
        noted.add(name)

    for metric, signal in signals.items():
        if _is_adverse_outlier(signal) and metric not in noted:
            return False, (
                f"signal '{metric}' is outside its normal range and adverse but "
                "no note explains it"
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
