"""Validation functions for ingest pipeline records.

Called by inserters before DuckDB INSERT to catch physically impossible values.
Raises pydantic.ValidationError on invalid data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from garmin_mcp.analysis.derivations import weighted_star_rating_raw
from garmin_mcp.validation.models import ActivityRecord, SplitRecord

# Summary star_rating must look like ``★★★★☆ 4.2/5.0``: 1-5 filled stars,
# 0-4 empty stars, then a ``N.N/5.0`` numeric rating. The captured group is the
# numeric rating, which must additionally fall within [0.0, 5.0].
_STAR_RATING_PATTERN = re.compile(r"^★{1,5}☆{0,4}\s*(\d+(?:\.\d+)?)/5\.0$")

# Verdict marks a transcribed ``prescription_verdict`` may carry (Issue #984),
# and the subset that asserts a deviation and therefore owes reasons.
_PRESCRIPTION_VERDICTS = frozenset({"✅", "🟡", "🔴"})
_PRESCRIPTION_DEVIATION_VERDICTS = frozenset({"🟡", "🔴"})

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
        - ``prescription_verdict`` (Issue #984) carries one of the three
          verdict marks, and a 🟡 / 🔴 verdict states at least one reason —
          a deviation asserted without its numbers is exactly the unsupported
          narration this guard exists to keep out of DuckDB

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

    verdict_block = analysis_data.get("prescription_verdict")
    errors.extend(_prescription_verdict_errors(verdict_block))

    return (not errors), errors


def _prescription_verdict_errors(verdict_block: Any) -> list[str]:
    """Errors in a transcribed ``prescription_verdict`` (empty when absent/ok).

    The block is computed by ``compute_prescription_verdict`` and only
    transcribed by the agent, so anything outside the deterministic shape means
    the transcription drifted.
    """
    if verdict_block is None:
        return []
    if not isinstance(verdict_block, dict):
        return [f"prescription_verdict must be an object, got {verdict_block!r}"]

    errors: list[str] = []
    verdict = verdict_block.get("verdict")
    if verdict not in _PRESCRIPTION_VERDICTS:
        errors.append(
            f"prescription_verdict.verdict {verdict!r} is not one of "
            f"{sorted(_PRESCRIPTION_VERDICTS)}"
        )

    reasons = verdict_block.get("reasons")
    stated = [r for r in reasons if str(r).strip()] if isinstance(reasons, list) else []
    if verdict in _PRESCRIPTION_DEVIATION_VERDICTS and not stated:
        errors.append(
            f"prescription_verdict.verdict={verdict} states no reasons "
            "(a deviation must say which of volume / HR / intensity deviated)"
        )
    return errors


# Sections whose star_rating is a weighted average the guard can recompute.
_WEIGHTED_STAR_SECTIONS = frozenset({"summary", "phase", "environment"})

# Max tolerated |raw_mean - stated| difference: half a display step (0.05) plus
# a float epsilon (Issue #859). The stated rating is compared against the
# *unrounded* weighted mean, not a re-rounded value: a correctly-rounded
# 1-decimal display is at most 0.05 from the true mean, so both roundings of an
# ``X.X5`` boundary pass, while genuine arithmetic errors (>= 0.1 off) still
# fail. The epsilon absorbs binary float representation error at the boundary.
_STAR_WEIGHTING_TOLERANCE = 0.05
_FLOAT_EPS = 1e-9


def check_star_weighting_consistency(
    section_type: str, analysis_data: dict[str, Any]
) -> tuple[bool, str | None]:
    """Verify the stated star_rating against its weighted-axis breakdown.

    Deterministic guard for the LLM-computed weighted star ratings (summary
    4-axis, phase, environment; Issue #706). When ``analysis_data`` carries a
    ``star_rating_breakdown`` object::

        {"axis_scores": {...}, "weights": {...}, "star_rating": 3.7}

    the true weighted mean is computed with
    :func:`garmin_mcp.analysis.derivations.weighted_star_rating_raw` (unrounded)
    and compared against the stated value. The stated value is the breakdown's
    numeric ``star_rating`` when present, otherwise the numeric part of the
    top-level ``star_rating`` string (``★★★★☆ 3.7/5.0``).

    Args:
        section_type: The section type of the analysis JSON.
        analysis_data: The section's ``analysis_data`` dict.

    Returns:
        ``(True, None)`` when consistent, or when the check does not apply
        (section types without weighted ratings). For weighted-star sections
        (summary / phase / environment) the breakdown is **mandatory** and the
        check is fail-closed (Issue #751): ``(False, reason)`` when the
        breakdown is missing, not an object, lacks ``axis_scores`` / ``weights``
        objects, is malformed, or the stated rating differs from the true
        weighted mean by more than half a display step (0.05). A weighted-star
        section whose breakdown carries
        valid axis scores + weights but no stated rating still passes (nothing
        to compare against).
    """
    if section_type not in _WEIGHTED_STAR_SECTIONS:
        return True, None

    breakdown = analysis_data.get("star_rating_breakdown")
    if not isinstance(breakdown, dict):
        return False, (
            f"star_rating_breakdown is required for weighted-star section "
            f"'{section_type}' but is missing or not an object"
        )
    axis_scores = breakdown.get("axis_scores")
    weights = breakdown.get("weights")
    if not isinstance(axis_scores, dict) or not isinstance(weights, dict):
        return False, (
            f"star_rating_breakdown for weighted-star section '{section_type}' "
            "must contain 'axis_scores' and 'weights' objects"
        )

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
        raw_mean = weighted_star_rating_raw(axis_scores, weights)
    except (TypeError, ValueError) as e:
        return False, f"star_rating_breakdown is malformed: {e}"

    if abs(raw_mean - stated) > _STAR_WEIGHTING_TOLERANCE + _FLOAT_EPS:
        return False, (
            f"star_rating {stated} does not match the weighted mean "
            f"{raw_mean} from star_rating_breakdown "
            f"(axis_scores={axis_scores}, weights={weights})"
        )
    return True, None


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
    pure guard -- data in, ``(ok, reason)`` out, same return style as
    :func:`check_star_weighting_consistency` -- rejects a section when:

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
