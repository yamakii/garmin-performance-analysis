"""What a run is *for*: the purpose vocabulary and a pure resolver (Issue #1312).

``session_type`` says what kind of session a prescription row is, but a long
run may be an aerobic long run or a goal-pace rehearsal, and the two are judged
differently. The **purpose** names that finer intent. Purposes are general
coaching categories, not one athlete's plan, so they also apply to runs of
users who never write a prescription.

:func:`resolve_purpose` returns the purpose of any run, first match wins:

1. the prescription's own ``purpose``            -> ``source="prescription"``
2. the default for its ``session_type``          -> ``source="session_default"``
3. inference from the run's own data             -> ``source="inferred"``
4. ``unknown``                                   -> ``source="default"``

Inference matters because a run without a prescription is the common case for
other users of this tool. ``source`` is exposed so the coach can hedge an
inferred purpose.

The module is pure: no I/O, no DB access.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Purpose:
    """One run purpose.

    Attributes:
        id: Stable identifier stored in ``weekly_prescriptions.purpose``.
        label_ja: Japanese display label.
        session_types: Prescription ``session_type`` values this purpose may be
            declared on. Empty for ``unknown``, which is never prescribed.
    """

    id: str
    label_ja: str
    session_types: frozenset[str]


def _purpose(id_: str, label_ja: str, *session_types: str) -> Purpose:
    return Purpose(id=id_, label_ja=label_ja, session_types=frozenset(session_types))


#: Every purpose, keyed by id.
PURPOSES: dict[str, Purpose] = {
    p.id: p
    for p in (
        _purpose("easy", "イージー", "easy", "recovery"),
        _purpose("recovery", "リカバリー", "recovery", "easy"),
        _purpose("long_easy", "ロング（有酸素）", "long"),
        _purpose("long_goal_pace", "ロング（目標ペース）", "long"),
        _purpose("long_fast_finish", "ロング（後半上げ）", "long"),
        _purpose("progression", "ビルドアップ", "easy", "long", "tempo"),
        _purpose("tempo", "テンポ", "tempo", "threshold"),
        _purpose("intervals", "インターバル", "threshold", "tempo"),
        _purpose("fartlek", "ファルトレク", "easy", "tempo", "threshold"),
        _purpose("race", "レース", "long", "tempo", "threshold"),
        _purpose("unknown", "不明"),
    )
}

#: Purpose a prescription row gets when it declares none.
DEFAULT_PURPOSE_BY_SESSION: dict[str, str] = {
    "easy": "easy",
    "recovery": "recovery",
    "long": "long_easy",
    "tempo": "tempo",
    "threshold": "intervals",
}

#: Moving time (minutes) from which an unprescribed run is read as a long run.
LONG_RUN_MIN_MINUTES: int = 90

#: Keys a prescription's ``allowances`` object may carry.
ALLOWANCE_KEYS: frozenset[str] = frozenset({"walk"})

PurposeSource = Literal["prescription", "session_default", "inferred", "default"]


@dataclass(frozen=True)
class ResolvedPurpose:
    """The purpose of one run and where it came from."""

    id: str
    label_ja: str
    source: PurposeSource


def _resolved(purpose_id: str, source: PurposeSource) -> ResolvedPurpose:
    return ResolvedPurpose(
        id=purpose_id, label_ja=PURPOSES[purpose_id].label_ja, source=source
    )


def _is_race_name(name: Any) -> bool:
    """Whether an activity name marks a race (shared fragments, #982)."""
    if not name:
        return False
    from garmin_mcp.database.readers.durability import _RACE_NAME_FRAGMENTS

    lowered = str(name).lower()
    return any(fragment.lower() in lowered for fragment in _RACE_NAME_FRAGMENTS)


def _is_race(run: Mapping[str, Any]) -> bool:
    """A race: the goal race's day, or a race-like name run at a race effort.

    A name alone is not enough (#1322): Garmin's coached 「レース前ワークアウト」
    (a pre-race tune-up) and a 2 km 「親子マラソン」 run beside a child carry
    the fragments too, at an easy effort. Racing is hard running, so a
    name-only match also needs ``intensity_class >= 2``.
    """
    if run.get("is_goal_race_day"):
        return True
    intensity_class = run.get("intensity_class")
    return (
        _is_race_name(run.get("activity_name"))
        and intensity_class is not None
        and int(intensity_class) >= 2
    )


def _infer(run: Mapping[str, Any]) -> str | None:
    """Infer a purpose from the run's own data, or ``None`` with nothing to go on.

    First match wins: race, intervals, progression, long, tempo, recovery, easy.
    The ``easy`` fallback needs at least one measured fact (moving time or an
    intensity reading); a run with none of them stays ``unknown``.
    """
    if _is_race(run):
        return "race"
    if run.get("has_rep_structure"):
        return "intervals"
    if run.get("is_progression"):
        return "progression"

    moving_minutes = run.get("moving_minutes")
    intensity_class = run.get("intensity_class")
    intensity_category = run.get("intensity_category")

    if moving_minutes is not None and float(moving_minutes) >= LONG_RUN_MIN_MINUTES:
        if intensity_class is not None and int(intensity_class) >= 2:
            return "long_goal_pace"
        return "long_easy"
    if intensity_class is not None and int(intensity_class) == 2:
        return "tempo"
    # Garmin's own label: the canonical intensity category folds ``recovery``
    # into ``easy``, so only the raw training type can tell them apart (#1322).
    if str(run.get("training_type") or "").strip().lower() == "recovery":
        return "recovery"
    if (
        moving_minutes is not None
        or intensity_class is not None
        or intensity_category is not None
    ):
        return "easy"
    return None


def resolve_purpose(
    prescription: Mapping[str, Any] | None,
    run: Mapping[str, Any],
) -> ResolvedPurpose:
    """Return the purpose of a run.

    Args:
        prescription: The day's prescription row (``session_type`` and optional
            ``purpose``), or ``None`` when the run had no prescription.
        run: Facts about the run: ``activity_name``, ``moving_minutes``,
            ``intensity_class`` (from ``derivations.intensity_class``),
            ``intensity_category`` (from ``resolve_intensity_category``),
            ``has_rep_structure``, ``is_progression`` and ``is_goal_race_day``,
            plus ``training_type`` (Garmin's raw label, for recovery) and
            ``is_marked_progression`` (the prescription names a build-up and
            the run shows one). Missing keys count as unknown.

    Returns:
        The resolved purpose with its Japanese label and source.
    """
    if prescription is not None:
        declared = prescription.get("purpose")
        if declared in PURPOSES and declared != "unknown":
            return _resolved(str(declared), "prescription")
        # Evidence stronger than the session type alone (#1322). A row written
        # before ``purpose`` existed only says ``long`` or ``tempo``; the goal
        # race's own day, or a build-up the prescription names *and* the run
        # shows, is what the run was for. A progression read off the data
        # alone never overrides the plan: HR drift with a quick last km on an
        # easy long run would otherwise turn its walk breaks into concerns.
        if run.get("is_goal_race_day"):
            return _resolved("race", "inferred")
        if run.get("is_marked_progression"):
            return _resolved("progression", "prescription")
        default = DEFAULT_PURPOSE_BY_SESSION.get(
            str(prescription.get("session_type") or "")
        )
        if default is not None:
            return _resolved(default, "session_default")

    inferred = _infer(run)
    if inferred is not None:
        return _resolved(inferred, "inferred")
    return _resolved("unknown", "default")
