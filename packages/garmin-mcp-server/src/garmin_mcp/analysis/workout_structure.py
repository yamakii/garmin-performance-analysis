"""Step structure of a prescription (Issue #1400, Epic #1398).

A prescription's workout is an ordered list of steps in the same generic
format that ``tools.workout_scheduling.build_workout_json`` /
``schedule_custom_workout`` accept, extended with a few judge-only keys.
Registration, judging and bookend accounting all read this one structure, so
what the watch was asked to do and what the run is judged against can never
drift apart.

Format:

- An executable step carries a ``step_type`` (``warmup`` / ``run`` /
  ``recovery`` / ``rest`` / ``cooldown``) and exactly one duration key
  (``duration_minutes`` / ``duration_seconds`` / ``distance_m``), optionally
  ``hr_low`` / ``hr_high`` in bpm.
- A repeat group is ``{"repeat_count": n, "steps": [...]}``; groups nest at
  most two levels deep (a superset: ``2 x (3 x (run, rest), recovery)``).
- Judge-only keys never reach the watch: ``pace_low_s_per_km`` /
  ``pace_high_s_per_km`` (the watch stays HR-led), ``label`` and
  ``optional``. An ``optional`` step (a fast-finish branch) is allowed only on
  a top-level ``run`` step and is dropped from the registered workout.

Heart rate is stored in **bpm only**, never as a zone label: the athlete's
Garmin zone boundaries drift (114 distinct boundary sets in the history, and
they moved again between 2026-09-15 and 2026-09-25), so a "Z4" written today
would mean a different band by the time the run is judged.

Legacy prescription rows without a stored structure are synthesized from their
columns (:func:`synthesize_structure`), which is exactly the workout the
scheduler has always registered.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast

from garmin_mcp.analysis.prescription_shape import (
    BOOKENDED_TYPES,
    COOLDOWN_MINUTES,
    FINAL_EASY_MINUTES,
    STRIDES_DEFAULT_RECOVERY_SECONDS,
    STRIDES_DEFAULT_RUN_SECONDS,
    WARMUP_MINUTES,
    strides_block_seconds,
)

StepType = Literal["warmup", "run", "recovery", "rest", "cooldown"]


class Step(TypedDict, total=False):
    """One executable step (exactly one duration key)."""

    step_type: StepType
    duration_minutes: float
    duration_seconds: int
    distance_m: int
    hr_low: int
    hr_high: int
    pace_low_s_per_km: int
    pace_high_s_per_km: int
    label: str
    optional: bool


class RepeatGroup(TypedDict):
    """A repeat group: ``steps`` run ``repeat_count`` times."""

    repeat_count: int
    steps: list[Step | RepeatGroup]


Structure = list[Step | RepeatGroup]


@dataclass(frozen=True)
class FlatStep:
    """An executable step with the FIT ``workout_step_index`` it gets.

    Attributes:
        fit_index: The step's index in the FIT workout (and so the
            ``workout_step_index`` its laps carry).
        path: Index path of the step inside the structure (``(1, 0)`` = first
            child of the second top-level item).
        step: The step itself.
        group_path: Path of the innermost enclosing repeat group, ``None`` for
            a top-level step.
        repeat_count: How many times the step runs in total (the product of
            every enclosing ``repeat_count``; ``1`` for a top-level step).
    """

    fit_index: int
    path: tuple[int, ...]
    step: Mapping[str, Any]
    group_path: tuple[int, ...] | None
    repeat_count: int


#: Prescription session types that map onto a running workout. rest /
#: strength / cross are prescribed but never registered as a run. Strides are
#: not a session type: they ride on an easy row as its ``strides`` add-on.
RUN_SESSION_TYPES: frozenset[str] = frozenset(
    {"long", "easy", "recovery", "threshold", "tempo"}
)

_STEP_TYPES: frozenset[str] = frozenset(
    {"warmup", "run", "recovery", "rest", "cooldown"}
)
_DURATION_KEYS: tuple[str, ...] = ("duration_minutes", "duration_seconds", "distance_m")
_HR_KEYS: tuple[str, str] = ("hr_low", "hr_high")
_PACE_KEYS: tuple[str, str] = ("pace_low_s_per_km", "pace_high_s_per_km")
#: Keys that are judged (or only annotate) and never reach the watch.
_JUDGE_ONLY_KEYS: frozenset[str] = frozenset({*_PACE_KEYS, "label", "optional"})
_STEP_KEYS: frozenset[str] = frozenset(
    {"step_type", *_DURATION_KEYS, *_HR_KEYS, *_JUDGE_ONLY_KEYS}
)
_GROUP_KEYS: frozenset[str] = frozenset({"repeat_count", "steps"})

_HR_MIN, _HR_MAX = 60, 230
_PACE_MIN, _PACE_MAX = 150, 900
_REPEAT_MIN, _REPEAT_MAX = 1, 30
#: Deepest allowed nesting of repeat groups (a group inside a group).
_MAX_GROUP_DEPTH = 2


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_band(
    step: Mapping[str, Any],
    keys: tuple[str, str],
    lo: int,
    hi: int,
    unit: str,
    where: str,
) -> None:
    for key in keys:
        if key not in step:
            continue
        value = step[key]
        if not _is_int(value):
            raise ValueError(f"{where}: {key} must be an integer {unit}, got {value!r}")
        if not lo <= value <= hi:
            raise ValueError(f"{where}: {key} {value} is outside {lo}..{hi} {unit}")
    low_key, high_key = keys
    if low_key in step and high_key in step and step[low_key] > step[high_key]:
        raise ValueError(
            f"{where}: {low_key} {step[low_key]} is above {high_key} {step[high_key]}"
        )


def _validate_step(step: Mapping[str, Any], *, top_level: bool, where: str) -> None:
    unknown = set(step) - _STEP_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown step keys {sorted(unknown)}")
    step_type = step.get("step_type")
    if step_type not in _STEP_TYPES:
        raise ValueError(
            f"{where}: step_type must be one of {sorted(_STEP_TYPES)}, "
            f"got {step_type!r}"
        )
    durations = [key for key in _DURATION_KEYS if key in step]
    if len(durations) != 1:
        raise ValueError(
            f"{where}: a step needs exactly one of {list(_DURATION_KEYS)}, "
            f"got {durations or 'none'}"
        )
    (duration_key,) = durations
    duration = step[duration_key]
    valid_type = (
        _is_number(duration)
        if duration_key == "duration_minutes"
        else _is_int(duration)
    )
    if not valid_type or duration <= 0:
        raise ValueError(f"{where}: {duration_key} must be positive, got {duration!r}")
    _check_band(step, _HR_KEYS, _HR_MIN, _HR_MAX, "bpm", where)
    _check_band(step, _PACE_KEYS, _PACE_MIN, _PACE_MAX, "s/km", where)
    if "label" in step and not isinstance(step["label"], str):
        raise ValueError(f"{where}: label must be a string")
    if "optional" in step:
        if not isinstance(step["optional"], bool):
            raise ValueError(f"{where}: optional must be a boolean")
        if step["optional"] and not (top_level and step_type == "run"):
            raise ValueError(
                f"{where}: optional is allowed only on a top-level run step"
            )


def _validate_items(
    items: Any, *, depth: int, path: tuple[int, ...], title: str
) -> None:
    where = f"{title!r} step {'.'.join(map(str, path)) or 'root'}"
    if not isinstance(items, list) or not items:
        raise ValueError(f"{where}: steps must be a non-empty list")
    for i, item in enumerate(items):
        item_path = (*path, i)
        item_where = f"{title!r} step {'.'.join(map(str, item_path))}"
        if not isinstance(item, Mapping):
            raise ValueError(f"{item_where}: a step must be an object, got {item!r}")
        if "repeat_count" in item or "steps" in item:
            unknown = set(item) - _GROUP_KEYS
            if unknown:
                raise ValueError(
                    f"{item_where}: unknown repeat-group keys {sorted(unknown)}"
                )
            if depth >= _MAX_GROUP_DEPTH:
                raise ValueError(
                    f"{item_where}: repeat groups nest at most {_MAX_GROUP_DEPTH} deep"
                )
            count: Any = item.get("repeat_count")
            if not (_is_int(count) and _REPEAT_MIN <= count <= _REPEAT_MAX):
                raise ValueError(
                    f"{item_where}: repeat_count must be an integer "
                    f"{_REPEAT_MIN}..{_REPEAT_MAX}, got {count!r}"
                )
            _validate_items(
                item.get("steps"), depth=depth + 1, path=item_path, title=title
            )
        else:
            _validate_step(item, top_level=depth == 0, where=item_where)


def validate_structure(structure: Any, *, title: str) -> Structure:
    """Validate a prescription step structure and return it unchanged.

    Rules: every executable step has a known ``step_type`` and exactly one
    duration key; ``hr_low`` / ``hr_high`` are integer bpm in 60..230 with
    low <= high (zone labels are rejected); pace bounds are integer s/km in
    150..900 with low <= high; ``repeat_count`` is 1..30; repeat groups nest at
    most two deep; ``optional`` sits only on a top-level ``run`` step; unknown
    keys are rejected.

    Args:
        structure: The candidate structure (a list of steps / repeat groups).
        title: Name of the prescription, used in error messages.

    Returns:
        ``structure`` itself.

    Raises:
        ValueError: On the first rule a step breaks, naming ``title`` and the
            step's index path.
    """
    _validate_items(structure, depth=0, path=(), title=title)
    return structure  # type: ignore[no-any-return]


# ----------------------------------------------------------------------------
# Synthesis from legacy columns
# ----------------------------------------------------------------------------


def _stored_structure(row: Mapping[str, Any]) -> Any:
    raw = row.get("structure")
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else None
    return raw


def _easy_with_strides_structure(
    row: Mapping[str, Any], strides: Mapping[str, Any], hr_target: dict[str, Any]
) -> Structure:
    """Build an easy run with strides: opening easy, strides, final easy.

    ``target_minutes`` stays the total of the run, so the opening segment is
    whatever the strides block and the final
    :data:`~garmin_mcp.analysis.prescription_shape.FINAL_EASY_MINUTES` leave
    over. Only the two easy segments carry the HR target; strides and their
    jogs are too short for HR to settle.

    Raises:
        ValueError: When the row has no ``target_minutes`` or the strides leave
            no room for an opening easy segment.
    """
    target_minutes = row.get("target_minutes")
    if target_minutes is None:
        raise ValueError(
            "an easy session with strides needs target_minutes (the run total) "
            "to build a workout"
        )
    block = strides_block_seconds(strides)
    final_seconds = FINAL_EASY_MINUTES * 60
    opening_seconds = round(float(target_minutes) * 60) - block - final_seconds
    if opening_seconds <= 0:
        raise ValueError(
            f"strides take {block}s and the final easy segment "
            f"{FINAL_EASY_MINUTES}min, leaving no opening easy running inside "
            f"target_minutes {target_minutes}"
        )
    run_seconds = strides.get("run_seconds") or STRIDES_DEFAULT_RUN_SECONDS
    recovery_seconds = (
        strides.get("recovery_seconds") or STRIDES_DEFAULT_RECOVERY_SECONDS
    )
    steps: list[dict[str, Any]] = [
        {"step_type": "run", "duration_seconds": opening_seconds, **hr_target},
        {
            "repeat_count": int(strides["reps"]),
            "steps": [
                {"step_type": "run", "duration_seconds": int(run_seconds)},
                {"step_type": "recovery", "duration_seconds": int(recovery_seconds)},
            ],
        },
        {"step_type": "cooldown", "duration_minutes": FINAL_EASY_MINUTES, **hr_target},
    ]
    return cast(Structure, steps)


def synthesize_structure(row: Mapping[str, Any]) -> Structure | None:
    """Return the step structure of one ``weekly_prescriptions`` row.

    Precedence:

    1. A stored ``structure`` (list or JSON string) is validated and returned
       verbatim.
    2. An ``easy`` row with a ``strides`` add-on: an opening easy step, a
       repeat group of ``reps`` x (stride / jog) and a final 5-minute easy
       ``cooldown``, summing to exactly ``target_minutes``.
    3. A bookended quality session (threshold / tempo): a 10-minute warmup and
       a 5-minute cooldown around the body step.
    4. Anything else that runs (long / easy / recovery): a single body step
       ending on ``target_minutes`` or ``target_km`` (in meters), carrying
       ``hr_low`` only when the row prescribes a floor (#979, #1039).

    Args:
        row: A prescription row (``session_type``, ``title``,
            ``target_minutes`` / ``target_km``, ``hr_low`` / ``hr_high``,
            optional ``strides`` / ``structure``).

    Returns:
        The structure, or ``None`` for a session that is not a run (rest /
        strength / cross) or a run with no volume (neither ``target_minutes``
        nor ``target_km``).

    Raises:
        ValueError: When a stored structure is invalid, or an easy row's
            strides do not fit inside ``target_minutes``.
    """
    session_type = str(row.get("session_type") or "")
    if session_type not in RUN_SESSION_TYPES:
        return None

    stored = _stored_structure(row)
    if stored is not None:
        title = str(row.get("title") or session_type)
        return validate_structure(stored, title=title)

    hr_target: dict[str, Any] = {}
    if row.get("hr_low") is not None:
        hr_target["hr_low"] = row["hr_low"]
    if row.get("hr_high") is not None:
        hr_target["hr_high"] = row["hr_high"]

    strides = row.get("strides")
    if session_type == "easy" and strides:
        return _easy_with_strides_structure(row, strides, hr_target)

    body: dict[str, Any] = {"step_type": "run"}
    target_minutes = row.get("target_minutes")
    target_km = row.get("target_km")
    if target_minutes is not None:
        body["duration_minutes"] = target_minutes
    elif target_km is not None:
        body["distance_m"] = round(float(target_km) * 1000)
    else:
        return None
    body.update(hr_target)

    steps: list[dict[str, Any]] = [body]
    if session_type in BOOKENDED_TYPES:
        steps = [
            {"step_type": "warmup", "duration_minutes": WARMUP_MINUTES},
            body,
            {"step_type": "cooldown", "duration_minutes": COOLDOWN_MINUTES},
        ]
    return cast(Structure, steps)


# ----------------------------------------------------------------------------
# Registration, FIT indices and totals
# ----------------------------------------------------------------------------


def _is_group(item: Mapping[str, Any]) -> bool:
    return "repeat_count" in item


def _is_optional(item: Mapping[str, Any]) -> bool:
    return not _is_group(item) and bool(item.get("optional"))


def _registrable_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if _is_optional(item):
            continue
        if _is_group(item):
            out.append(
                {
                    "repeat_count": item["repeat_count"],
                    "steps": _registrable_items(item["steps"]),
                }
            )
        else:
            out.append({k: v for k, v in item.items() if k not in _JUDGE_ONLY_KEYS})
    return out


def registrable_steps(structure: Structure) -> list[dict[str, Any]]:
    """Return the steps to send to the watch.

    Optional steps are dropped and the judge-only keys (pace bounds, ``label``,
    ``optional``) are stripped, so the result is exactly the generic steps
    format ``build_workout_json`` / ``schedule_custom_workout`` accept.
    """
    return _registrable_items(structure)  # type: ignore[arg-type]


def registration_fingerprint(row: Mapping[str, Any]) -> str | None:
    """Canonical JSON of what the watch would receive for one prescription row.

    The title plus the registrable steps, built by the same
    :func:`synthesize_structure` → :func:`registrable_steps` path registration
    uses (``tools.workout_scheduling.build_steps_from_prescription``), so no
    field list is kept by hand: judge-only fields (``rationale``, ``rating``,
    ``allowances``, ``purpose``, pace bounds) never change it, while targets,
    HR bounds, strides, a stored structure or the title do. Two rows with equal
    fingerprints put the same workout on the watch (#1447).

    Returns:
        The fingerprint, or ``None`` when the row cannot be registered as a
        run (not a run session, no volume, or an invalid structure).
    """
    if str(row.get("session_type") or "") not in RUN_SESSION_TYPES:
        return None
    try:
        structure = synthesize_structure(row)
    except ValueError:
        return None
    if structure is None:
        return None
    return json.dumps(
        {"title": str(row.get("title") or ""), "steps": registrable_steps(structure)},
        sort_keys=True,
        ensure_ascii=False,
    )


def fit_step_indices(structure: Structure) -> list[FlatStep]:
    """Return every registered executable step with its FIT step index.

    The FIT workout lists a repeat group's children first and the repeat
    marker after them, so the marker takes the index following its last child:
    ``[WU, 4 x (run, rec), CD]`` gives WU 0, run 1, rec 2, (marker 3), CD 4.
    Optional steps are not registered, so they take no index and are left out.
    """
    flat: list[FlatStep] = []

    def walk(
        items: Sequence[Mapping[str, Any]],
        path: tuple[int, ...],
        group_path: tuple[int, ...] | None,
        multiplier: int,
        next_index: int,
    ) -> int:
        for i, item in enumerate(items):
            item_path = (*path, i)
            if _is_optional(item):
                continue
            if _is_group(item):
                next_index = walk(
                    item["steps"],
                    item_path,
                    item_path,
                    multiplier * int(item["repeat_count"]),
                    next_index,
                )
                next_index += 1  # the repeat marker
            else:
                flat.append(
                    FlatStep(
                        fit_index=next_index,
                        path=item_path,
                        step=item,
                        group_path=group_path,
                        repeat_count=multiplier,
                    )
                )
                next_index += 1
        return next_index

    walk(structure, (), None, 1, 0)  # type: ignore[arg-type]
    return flat


def structure_totals(structure: Structure) -> tuple[float | None, float | None]:
    """Return the ``(seconds, km)`` the registered structure adds up to.

    A fully timed structure yields ``(seconds, None)``, a fully distance-based
    one ``(None, km)``; a structure mixing both cannot be totalled in either
    unit and yields ``(None, None)``. Optional steps are not counted.
    """
    seconds = 0.0
    meters = 0.0
    timed = False
    distanced = False
    for flat in fit_step_indices(structure):
        step = flat.step
        if "duration_minutes" in step:
            seconds += float(step["duration_minutes"]) * 60 * flat.repeat_count
            timed = True
        elif "duration_seconds" in step:
            seconds += float(step["duration_seconds"]) * flat.repeat_count
            timed = True
        elif "distance_m" in step:
            meters += float(step["distance_m"]) * flat.repeat_count
            distanced = True
    if timed and distanced:
        return None, None
    if timed:
        return seconds, None
    if distanced:
        return None, meters / 1000
    return None, None
