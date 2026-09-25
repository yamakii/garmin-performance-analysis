"""Training plan ledger DB inserter.

Persists the two plan concepts introduced in issue #977:

- ``training_blocks`` — the mesocycle ledger. Saves are 洗い替え (DELETE +
  INSERT per ``user_id``, ``sequence`` following list order), mirroring
  ``athlete_goals``; every save also appends a JSON snapshot of the whole list
  to ``training_block_versions`` so overwritten plans stay recoverable.
- ``weekly_prescriptions`` — one row per prescribed session per day, and the
  single source of the per-day plan including its coach verdict (``rating`` /
  ``rationale``, Issue #1021). Saves are append-only per ``batch_id`` (one save
  = one batch, latest batch per week is canonical) and a revision must be
  paired with a new review version (:func:`_check_revision_guard`); only
  ``status`` and the Garmin / activity ids are mutated later, via
  :func:`update_prescription_status`.

Validation is deliberately strict and raises ``ValueError`` up front: these rows
are written by an LLM-driven skill, so a malformed date range or session type
must fail loudly rather than land silently in the ledger.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: Phases a training block may declare.
ALLOWED_PHASES = frozenset(
    {"base", "build", "peak", "taper", "race", "recovery", "cutback"}
)

#: Session types a weekly prescription may declare.
ALLOWED_SESSION_TYPES = frozenset(
    {
        "long",
        "easy",
        "recovery",
        "threshold",
        "tempo",
        "rest",
        "strength",
        "cross",
    }
)

#: Lifecycle states of a prescription row.
ALLOWED_STATUSES = frozenset(
    {"prescribed", "registered", "done", "replaced", "skipped"}
)

#: Coach verdicts a prescription row may carry (``None`` = ungraded).
ALLOWED_RATINGS = frozenset({"✅", "🟡", "🔴"})

#: Slowest plausible average pace (seconds per km) for a registered bookended
#: session — body plus its warmup/cooldown minutes over the whole distance. A
#: Z3-Z4 body wrapped in easy jogging never averages slower than this, so a row
#: above it wrote ``target_minutes`` as the session total (Issue #1084).
BOOKENDED_PACE_SLOW_S_PER_KM = 480.0

#: Fastest plausible average pace (seconds per km) for the same figure; below it
#: the two targets disagree by more than a mis-encoded total can explain.
BOOKENDED_PACE_FAST_S_PER_KM = 180.0


def _default_db_path() -> str:
    """Resolve the default DuckDB path (never hard-coded by callers)."""
    from garmin_mcp.utils.paths import get_database_dir

    return str(get_database_dir() / "garmin_performance.duckdb")


def _parse_date(value: Any, field: str) -> date:
    """Parse ``value`` into a ``date``, raising ValueError with ``field`` context."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"{field} must be a YYYY-MM-DD date, got {value!r}"
            ) from exc
    raise ValueError(f"{field} is required and must be a YYYY-MM-DD date")


def _format_pace(seconds_per_km: float) -> str:
    """Render a seconds-per-km pace as ``m:ss`` for an error message."""
    total = int(round(seconds_per_km))
    return f"{total // 60}:{total % 60:02d}"


def _validate_bookended_targets(
    title: str, session_type: str, target_minutes: Any, target_km: Any
) -> None:
    """Reject a quality row whose ``target_minutes`` was written as the total.

    ``threshold`` / ``tempo`` rows prescribe the **body** in ``target_minutes``
    — the builder wraps it in :func:`~garmin_mcp.analysis.prescription_shape.
    bookend_minutes` of warmup/cooldown — while ``target_km`` always describes
    the **whole** session. Both conventions are documented, but nothing enforced
    them, so a row written entirely as totals (55 min / 8.0 km) stayed
    self-consistent on its face and only surfaced later as a bogus ``replaced``
    verdict out of ``reconcile_prescriptions`` (Issue #1084).

    The discriminator is the implied average pace of the workout that actually
    gets registered: body plus bookends over the whole distance. A Z3-Z4 body
    wrapped in easy jogging cannot average slower than
    :data:`BOOKENDED_PACE_SLOW_S_PER_KM`, and a total-encoded row always does.

    Rows that cannot be compared are left alone: non-bookended session types
    (whose ``target_minutes`` is the total by convention), rows missing either
    target, and a non-positive ``target_km``.

    Args:
        title: Row title, quoted into the error message.
        session_type: The row's session type.
        target_minutes: Prescribed minutes (the body, by convention).
        target_km: Prescribed distance (the whole session, by convention).

    Raises:
        ValueError: When the implied pace falls outside the plausible band.
    """
    from garmin_mcp.analysis.prescription_shape import bookend_minutes

    if target_minutes is None or target_km is None:
        return
    bookends = bookend_minutes(session_type)
    if not bookends:
        return
    km = float(target_km)
    if km <= 0:
        return

    implied = (float(target_minutes) + bookends) * 60.0 / km
    if BOOKENDED_PACE_FAST_S_PER_KM <= implied <= BOOKENDED_PACE_SLOW_S_PER_KM:
        return
    raise ValueError(
        f"prescription {title!r}: target_minutes {target_minutes} with "
        f"target_km {target_km} implies {_format_pace(implied)}/km across the "
        f"whole registered session (body + {bookends}min warmup/cooldown), "
        f"outside the plausible {_format_pace(BOOKENDED_PACE_FAST_S_PER_KM)}-"
        f"{_format_pace(BOOKENDED_PACE_SLOW_S_PER_KM)}/km band. For "
        f"{session_type} rows target_minutes is the BODY only, while target_km "
        f"is the WHOLE session — a total written into both is the usual cause"
    )


#: Inclusive bounds of each ``strides`` field (reps / seconds).
_STRIDES_BOUNDS: dict[str, tuple[int, int]] = {
    "reps": (2, 8),
    "run_seconds": (10, 30),
    "recovery_seconds": (60, 180),
}


def _validate_strides(row: Mapping[str, Any]) -> dict[str, int] | None:
    """Validate an easy row's ``strides`` add-on and return it with defaults.

    Strides are a neuromuscular stimulus placed inside an easy run, not a
    session of their own (Issue #1295). The watch workout puts them between an
    opening easy segment of at least ``MIN_OPENING_EASY_MINUTES`` and a final
    ``FINAL_EASY_MINUTES``, with ``target_minutes`` staying the **total** of the
    run, so the row must leave room for both segments around the block.

    Args:
        row: A prescription row; only its ``strides``, ``session_type``,
            ``target_minutes`` and ``title`` are read.

    Returns:
        ``{"reps", "run_seconds", "recovery_seconds"}`` with the defaults filled
        in, or ``None`` when the row carries no ``strides``.

    Raises:
        ValueError: When ``strides`` is set on a non-easy row, is not an object,
            carries an unknown key, a non-integer or out-of-range value, or does
            not fit inside ``target_minutes``.
    """
    from garmin_mcp.analysis.prescription_shape import (
        FINAL_EASY_MINUTES,
        MIN_OPENING_EASY_MINUTES,
        STRIDES_DEFAULT_RECOVERY_SECONDS,
        STRIDES_DEFAULT_RUN_SECONDS,
        strides_block_seconds,
    )

    strides = row.get("strides")
    if strides is None:
        return None
    title = str(row.get("title") or "")
    if row.get("session_type") != "easy":
        raise ValueError(
            f"prescription {title!r}: strides can only be added to an easy "
            f"session, got session_type {row.get('session_type')!r}"
        )
    if not isinstance(strides, Mapping):
        raise ValueError(
            f"prescription {title!r}: strides must be an object "
            "{reps, run_seconds, recovery_seconds}"
        )
    unknown = sorted(set(strides) - set(_STRIDES_BOUNDS))
    if unknown:
        raise ValueError(
            f"prescription {title!r}: unknown strides keys {unknown} "
            f"(allowed: {sorted(_STRIDES_BOUNDS)})"
        )

    candidate: dict[str, Any] = {
        "reps": strides.get("reps"),
        "run_seconds": strides.get("run_seconds", STRIDES_DEFAULT_RUN_SECONDS),
        "recovery_seconds": strides.get(
            "recovery_seconds", STRIDES_DEFAULT_RECOVERY_SECONDS
        ),
    }
    for key, (low, high) in _STRIDES_BOUNDS.items():
        value = candidate[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"prescription {title!r}: strides.{key} must be an integer "
                f"in {low}..{high}, got {value!r}"
            )
        if not low <= value <= high:
            raise ValueError(
                f"prescription {title!r}: strides.{key} must be in "
                f"{low}..{high}, got {value}"
            )
    resolved: dict[str, int] = {key: int(value) for key, value in candidate.items()}

    block = strides_block_seconds(resolved)
    needed = (MIN_OPENING_EASY_MINUTES + FINAL_EASY_MINUTES) * 60 + block
    target_minutes = row.get("target_minutes")
    if target_minutes is None or float(target_minutes) * 60 < needed:
        raise ValueError(
            f"prescription {title!r}: strides {resolved['reps']}x"
            f"{resolved['run_seconds']}s/{resolved['recovery_seconds']}s take "
            f"{block}s, and with at least {MIN_OPENING_EASY_MINUTES}min of easy "
            f"running before and {FINAL_EASY_MINUTES}min after they need "
            f"target_minutes (the run total) of at least {needed / 60:g}, got "
            f"{target_minutes!r}"
        )
    return resolved


def _validate_purpose(row: Mapping[str, Any]) -> str | None:
    """Validate a row's ``purpose`` against the purpose vocabulary (Issue #1312).

    The purpose is the run's intent, finer than ``session_type`` (a ``long``
    row may be ``long_easy`` or ``long_goal_pace``), so it must be one of
    :data:`~garmin_mcp.analysis.run_purpose.PURPOSES` and compatible with the
    row's ``session_type``. ``unknown`` is never prescribed.

    Args:
        row: A prescription row; only ``purpose``, ``session_type`` and
            ``title`` are read.

    Returns:
        The purpose id, or ``None`` when the row declares none.

    Raises:
        ValueError: On an unknown purpose or one that does not fit the
            row's ``session_type``.
    """
    from garmin_mcp.analysis.run_purpose import PURPOSES

    purpose = row.get("purpose")
    if purpose is None:
        return None
    title = str(row.get("title") or "")
    known = sorted(p for p in PURPOSES if p != "unknown")
    if purpose not in known:
        raise ValueError(
            f"prescription {title!r}: purpose must be one of {known} or null, "
            f"got {purpose!r}"
        )
    session_type = row.get("session_type")
    compatible = PURPOSES[purpose].session_types
    if session_type not in compatible:
        raise ValueError(
            f"prescription {title!r}: purpose {purpose!r} does not fit "
            f"session_type {session_type!r} (allowed session types: "
            f"{sorted(compatible)})"
        )
    return str(purpose)


def _validate_allowances(row: Mapping[str, Any]) -> dict[str, bool] | None:
    """Validate a row's ``allowances`` object (``{"walk": bool}``, Issue #1312).

    Args:
        row: A prescription row; only ``allowances`` and ``title`` are read.

    Returns:
        The allowances dict, or ``None`` when the row declares none.

    Raises:
        ValueError: When ``allowances`` is not an object, carries an unknown
            key or a non-boolean value.
    """
    from garmin_mcp.analysis.run_purpose import ALLOWANCE_KEYS

    allowances = row.get("allowances")
    if allowances is None:
        return None
    title = str(row.get("title") or "")
    if not isinstance(allowances, Mapping):
        raise ValueError(
            f"prescription {title!r}: allowances must be an object like "
            '{"walk": true}'
        )
    unknown = sorted(set(allowances) - ALLOWANCE_KEYS)
    if unknown:
        raise ValueError(
            f"prescription {title!r}: unknown allowances keys {unknown} "
            f"(allowed: {sorted(ALLOWANCE_KEYS)})"
        )
    for key, value in allowances.items():
        if not isinstance(value, bool):
            raise ValueError(
                f"prescription {title!r}: allowances.{key} must be true or "
                f"false, got {value!r}"
            )
    return {str(key): bool(value) for key, value in allowances.items()}


#: Step types that bookend a quality session rather than belong to its body.
_BOOKEND_STEP_TYPES = frozenset({"warmup", "cooldown"})


def _validate_structure(row: dict[str, Any]) -> dict[str, Any]:
    """Validate a row's step ``structure`` and derive ``target_minutes`` from it.

    The structure is the workout the watch is asked to run (Issue #1401, see
    :mod:`garmin_mcp.analysis.workout_structure`). It is validated with
    :func:`~garmin_mcp.analysis.workout_structure.validate_structure` (bpm
    only, never a zone label), may only sit on a session type that runs, and
    cannot be combined with the ``strides`` add-on: strides are one way of
    describing an easy run's steps, the structure is the other, and carrying
    both would leave two sources for the same workout.

    When the row has no ``target_minutes`` and every registered step is timed,
    it is derived from the structure following the column's convention: the
    **body** only (every step but warmup / cooldown) for ``threshold`` /
    ``tempo`` rows, the **total** otherwise. ``hr_low`` / ``hr_high`` are
    never derived: a structure with several HR bands (a build-up) has no single
    band that stands for the whole run.

    Args:
        row: A prescription row; ``structure``, ``strides``, ``session_type``,
            ``target_minutes`` and ``title`` are read.

    Returns:
        ``row`` itself when it carries no structure or nothing is derived,
        otherwise a copy with ``target_minutes`` filled in.

    Raises:
        ValueError: On an invalid structure, a structure on a session type that
            does not run, or a row carrying both ``strides`` and ``structure``.
    """
    from garmin_mcp.analysis.prescription_shape import BOOKENDED_TYPES
    from garmin_mcp.analysis.workout_structure import (
        RUN_SESSION_TYPES,
        fit_step_indices,
        structure_totals,
        validate_structure,
    )

    structure = row.get("structure")
    if structure is None:
        return row
    title = str(row.get("title") or "")
    session_type = row.get("session_type")
    if session_type not in RUN_SESSION_TYPES:
        raise ValueError(
            f"prescription {title!r}: a structure can only be set on a run "
            f"session ({sorted(RUN_SESSION_TYPES)}), got session_type "
            f"{session_type!r}"
        )
    if row.get("strides") is not None:
        raise ValueError(
            f"prescription {title!r}: set either strides or structure, not both "
            "(write the strides as a repeat group inside the structure)"
        )
    validated = validate_structure(structure, title=title)

    if row.get("target_minutes") is not None:
        return row
    total_seconds, _ = structure_totals(validated)
    if total_seconds is None:
        return row
    if session_type in BOOKENDED_TYPES:
        seconds = 0.0
        for flat in fit_step_indices(validated):
            step = flat.step
            if step.get("step_type") in _BOOKEND_STEP_TYPES:
                continue
            if "duration_minutes" in step:
                seconds += float(step["duration_minutes"]) * 60 * flat.repeat_count
            else:
                seconds += float(step["duration_seconds"]) * flat.repeat_count
    else:
        seconds = total_seconds
    minutes = round(seconds / 60)
    if minutes <= 0:
        return row
    return {**row, "target_minutes": minutes}


def _validate_ladder(ladder: Any, block_title: str) -> list[dict[str, Any]]:
    """Validate the long-run ladder of a block and return it as a list.

    Each step needs ``week_start`` and exactly one of ``target_km`` /
    ``target_minutes`` (a ``None`` value counts as absent), so a ladder row can
    never be an untargeted placeholder.
    """
    if ladder is None:
        return []
    if not isinstance(ladder, list):
        raise ValueError(f"block {block_title!r}: long_run_ladder must be a list")

    for step in ladder:
        if not isinstance(step, dict):
            raise ValueError(f"block {block_title!r}: ladder step must be an object")
        _parse_date(step.get("week_start"), f"block {block_title!r}: week_start")
        has_km = step.get("target_km") is not None
        has_minutes = step.get("target_minutes") is not None
        if has_km == has_minutes:
            raise ValueError(
                f"block {block_title!r}: ladder step {step.get('week_start')!r} "
                "needs exactly one of target_km / target_minutes"
            )
    return ladder


def _json_or_none(value: Any) -> str | None:
    """Serialize a JSON-able column value, keeping ``None`` as SQL NULL."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def insert_training_blocks(
    blocks: list[dict[str, Any]],
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Replace all training blocks for ``user_id`` and snapshot the new list.

    The canonical rows are replaced wholesale (DELETE + INSERT) with
    ``sequence`` following the supplied list order, and the full list is
    appended to ``training_block_versions`` as one JSON snapshot.

    Args:
        blocks: Block dicts with ``phase``, ``title``, ``start_date``,
            ``end_date`` (required) plus optional ``purpose``, ``weight_mode``,
            ``quality_sessions_per_week``, ``quality_types`` (list),
            ``long_run_ladder`` (list of ``{week_start, target_km |
            target_minutes, hr_ceiling, kind, note}``), ``cutback_rule`` (dict)
            and ``notes``.
        user_id: Ledger owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``{"count": <blocks written>, "version_id": <snapshot version>}``.

    Raises:
        ValueError: On an invalid phase, an inverted date range, or a ladder
            step without ``week_start`` / a single target.
    """
    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    validated: list[tuple[dict[str, Any], date, date]] = []
    for block in blocks:
        title = str(block.get("title") or "")
        if not title:
            raise ValueError("every block needs a title")
        phase = block.get("phase")
        if phase not in ALLOWED_PHASES:
            raise ValueError(
                f"block {title!r}: phase must be one of "
                f"{sorted(ALLOWED_PHASES)}, got {phase!r}"
            )
        start = _parse_date(block.get("start_date"), f"block {title!r}: start_date")
        end = _parse_date(block.get("end_date"), f"block {title!r}: end_date")
        if start > end:
            raise ValueError(
                f"block {title!r}: start_date {start} is after end_date {end}"
            )
        _validate_ladder(block.get("long_run_ladder"), title)
        validated.append((block, start, end))

    with get_write_connection(db_path) as conn:
        conn.execute("DELETE FROM training_blocks WHERE user_id = ?", [user_id])
        for index, (block, start, end) in enumerate(validated, start=1):
            conn.execute(
                """
                INSERT INTO training_blocks (
                    block_id, user_id, sequence, phase, title, start_date,
                    end_date, purpose, weight_mode, quality_sessions_per_week,
                    quality_types, long_run_ladder, cutback_rule, notes
                ) VALUES (
                    nextval('seq_training_blocks_id'), ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                [
                    user_id,
                    index,
                    block.get("phase"),
                    block.get("title"),
                    start,
                    end,
                    block.get("purpose"),
                    block.get("weight_mode"),
                    block.get("quality_sessions_per_week"),
                    _json_or_none(block.get("quality_types")),
                    _json_or_none(block.get("long_run_ladder")),
                    _json_or_none(block.get("cutback_rule")),
                    block.get("notes"),
                ],
            )

        version_row = conn.execute(
            "SELECT nextval('seq_training_block_versions_id')"
        ).fetchone()
        version_id = int(version_row[0]) if version_row is not None else 0
        conn.execute(
            """
            INSERT INTO training_block_versions (version_id, user_id, blocks_data)
            VALUES (?, ?, ?)
            """,
            [version_id, user_id, json.dumps(blocks, ensure_ascii=False, default=str)],
        )

        logger.info(
            "Saved %d training blocks user_id=%s (version_id=%d)",
            len(blocks),
            user_id,
            version_id,
        )

    return {"count": len(blocks), "version_id": version_id}


def _check_revision_guard(
    conn: Any, week_start: date, review_id: int | None, user_id: str
) -> None:
    """Reject a prescription batch that is not paired with a review version.

    The prescriptions are the per-day plan (verdict included), so revising them
    without re-issuing the review prose is what let the two stores drift
    (Issue #1021). Once a week has a review, a batch must carry that week's
    latest ``review_id`` and each review version may own at most one batch.

    Args:
        conn: Open write connection.
        week_start: Week start of the batch being saved.
        review_id: ``review_id`` supplied by the caller (may be ``None``).
        user_id: Ledger owner identifier.

    Raises:
        ValueError: When the batch would supersede the week's plan without a
            new review version, or when ``review_id`` does not exist.
    """
    if review_id is not None:
        known = conn.execute(
            "SELECT 1 FROM weekly_reviews WHERE review_id = ? AND user_id = ?",
            [review_id, user_id],
        ).fetchone()
        if known is None:
            raise ValueError(
                f"review_id {review_id} does not exist for user {user_id!r}; "
                "save the review first (save_weekly_review) and pass the "
                "review_id it returns"
            )

    latest_row = conn.execute(
        "SELECT review_id FROM weekly_reviews "
        "WHERE user_id = ? AND week_start_date = ? "
        "ORDER BY created_at DESC, review_id DESC LIMIT 1",
        [user_id, week_start],
    ).fetchone()
    if latest_row is None:
        # No review for the week: an unlinked batch stays allowed.
        return

    latest_review_id = int(latest_row[0])
    if review_id is None:
        raise ValueError(
            f"week {week_start} already has a weekly review (review_id "
            f"{latest_review_id}); save a new review version "
            "(save_weekly_review) with the revised recommendations/overall "
            "first, then pass its review_id"
        )
    if review_id != latest_review_id:
        raise ValueError(
            f"review_id {review_id} is not the latest review of week "
            f"{week_start} (latest is {latest_review_id}); save a new review "
            "version (save_weekly_review) with the revised "
            "recommendations/overall first, then pass its review_id"
        )

    batch_row = conn.execute(
        "SELECT MAX(batch_id) FROM weekly_prescriptions "
        "WHERE user_id = ? AND week_start_date = ? AND review_id = ?",
        [user_id, week_start, review_id],
    ).fetchone()
    if batch_row is not None and batch_row[0] is not None:
        raise ValueError(
            f"week {week_start} already has prescription batch {int(batch_row[0])} "
            f"for review {review_id}; save a new review version "
            "(save_weekly_review) with the revised recommendations/overall "
            "first, then pass its review_id"
        )


def insert_weekly_prescriptions(
    week_start_date: str,
    prescriptions: list[dict[str, Any]],
    *,
    review_id: int | None = None,
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Insert one batch of prescriptions for a week (append-only).

    All rows share a freshly allocated ``batch_id``; earlier batches for the
    same week stay untouched and are simply superseded (the reader returns the
    highest ``batch_id`` per week).

    These rows are the single source of the per-day plan, verdict included
    (``rating`` / ``rationale``), so a revision must re-issue the review prose
    with it: once a week has a review, every batch must point at that week's
    **latest** review version and each version may own only one batch (Issue
    #1021). Weeks without a review keep accepting unlinked batches.

    Args:
        week_start_date: Week start (``YYYY-MM-DD``); every row's ``date`` must
            fall in ``[week_start_date, week_start_date + 6]``.
        prescriptions: Row dicts with ``date``, ``session_type``, ``title``
            (required) plus optional ``target_minutes``, ``target_km``,
            ``hr_low``, ``hr_high``, ``pace_low_s_per_km``,
            ``pace_high_s_per_km``, ``rationale``, ``rating`` (``✅`` / ``🟡``
            / ``🔴``), ``status`` and — on ``easy`` rows only — ``strides``
            (``{reps, run_seconds=20, recovery_seconds=90}``, see
            :func:`_validate_strides`), stored as JSON with the defaults filled,
            plus optional ``purpose`` (see :func:`_validate_purpose`),
            ``allowances`` (``{"walk": bool}``, stored as JSON) and
            ``structure`` (the step list, see :func:`_validate_structure`;
            stored as JSON, fills ``target_minutes`` when it is absent).
        review_id: ``weekly_reviews.review_id`` when saved by a weekly review.
        user_id: Ledger owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``{"batch_id": int, "count": int, "prescription_ids": list[int]}``.

    Raises:
        ValueError: On a date outside the week, an unknown ``session_type``,
            ``status`` or ``rating``, ``hr_low`` above ``hr_high``, a
            ``threshold`` / ``tempo`` row whose ``target_minutes`` reads as the
            session total rather than the body (:func:`
            _validate_bookended_targets`), an invalid ``strides`` add-on, an
            unknown or incompatible ``purpose``, invalid ``allowances``, an
            invalid ``structure`` (or one combined with ``strides``), or a
            revision that skips the review (see the revision guard above).
    """
    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    week_start = _parse_date(week_start_date, "week_start_date")
    week_end = week_start + timedelta(days=6)

    validated: list[
        tuple[
            dict[str, Any],
            date,
            dict[str, int] | None,
            str | None,
            dict[str, bool] | None,
        ]
    ] = []
    for row in prescriptions:
        title = str(row.get("title") or "")
        if not title:
            raise ValueError("every prescription needs a title")
        session_type = row.get("session_type")
        if session_type not in ALLOWED_SESSION_TYPES:
            raise ValueError(
                f"prescription {title!r}: session_type must be one of "
                f"{sorted(ALLOWED_SESSION_TYPES)}, got {session_type!r}"
            )
        row_date = _parse_date(row.get("date"), f"prescription {title!r}: date")
        if not (week_start <= row_date <= week_end):
            raise ValueError(
                f"prescription {title!r}: date {row_date} is outside the week "
                f"{week_start}..{week_end}"
            )
        status = row.get("status") or "prescribed"
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"prescription {title!r}: status must be one of "
                f"{sorted(ALLOWED_STATUSES)}, got {status!r}"
            )
        hr_low = row.get("hr_low")
        hr_high = row.get("hr_high")
        if hr_low is not None and hr_high is not None and hr_low > hr_high:
            raise ValueError(
                f"prescription {title!r}: hr_low {hr_low} is above hr_high {hr_high}"
            )
        rating = row.get("rating")
        if rating is not None and rating not in ALLOWED_RATINGS:
            raise ValueError(
                f"prescription {title!r}: rating must be one of "
                f"{sorted(ALLOWED_RATINGS)} or null, got {rating!r}"
            )
        row = _validate_structure(row)
        _validate_bookended_targets(
            title, str(session_type), row.get("target_minutes"), row.get("target_km")
        )
        strides = _validate_strides(row)
        purpose = _validate_purpose(row)
        allowances = _validate_allowances(row)
        validated.append((row, row_date, strides, purpose, allowances))

    prescription_ids: list[int] = []
    with get_write_connection(db_path) as conn:
        _check_revision_guard(conn, week_start, review_id, user_id)

        batch_row = conn.execute(
            "SELECT nextval('seq_weekly_prescription_batches')"
        ).fetchone()
        batch_id = int(batch_row[0]) if batch_row is not None else 0

        for row, row_date, strides, purpose, allowances in validated:
            id_row = conn.execute(
                "SELECT nextval('seq_weekly_prescriptions_id')"
            ).fetchone()
            prescription_id = int(id_row[0]) if id_row is not None else 0
            conn.execute(
                """
                INSERT INTO weekly_prescriptions (
                    prescription_id, batch_id, user_id, review_id,
                    week_start_date, date, session_type, title, target_minutes,
                    target_km, hr_low, hr_high, pace_low_s_per_km,
                    pace_high_s_per_km, rationale, rating, status, strides,
                    purpose, allowances, structure
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    prescription_id,
                    batch_id,
                    user_id,
                    review_id,
                    week_start,
                    row_date,
                    row.get("session_type"),
                    row.get("title"),
                    row.get("target_minutes"),
                    row.get("target_km"),
                    row.get("hr_low"),
                    row.get("hr_high"),
                    row.get("pace_low_s_per_km"),
                    row.get("pace_high_s_per_km"),
                    row.get("rationale"),
                    row.get("rating"),
                    row.get("status") or "prescribed",
                    _json_or_none(strides),
                    purpose,
                    _json_or_none(allowances),
                    _json_or_none(row.get("structure")),
                ],
            )
            prescription_ids.append(prescription_id)

        logger.info(
            "Saved %d prescriptions user_id=%s week_start_date=%s (batch_id=%d)",
            len(prescription_ids),
            user_id,
            week_start,
            batch_id,
        )

    return {
        "batch_id": batch_id,
        "count": len(prescription_ids),
        "prescription_ids": prescription_ids,
    }


def update_prescription_status(
    prescription_id: int,
    status: str,
    *,
    garmin_workout_id: int | None = None,
    garmin_schedule_id: int | None = None,
    actual_activity_id: int | None = None,
    registered_bookend_minutes: int | None = None,
    structure: list[dict[str, Any]] | None = None,
    db_path: str | None = None,
) -> bool:
    """Set a prescription's status (and optional ids), refreshing ``updated_at``.

    Only the ids that are supplied are written; omitted ones keep their stored
    value, so registering a Garmin workout and later linking the actual activity
    are independent updates.

    Args:
        prescription_id: Row identifier from ``insert_weekly_prescriptions``.
        status: One of ``prescribed`` / ``registered`` / ``done`` / ``replaced``
            / ``skipped``.
        garmin_workout_id: Garmin workout id to record (optional).
        garmin_schedule_id: Garmin schedule id to record (optional).
        actual_activity_id: Linked activity id to record (optional).
        registered_bookend_minutes: Warmup + cooldown minutes the registered
            workout actually carries, from
            :func:`~garmin_mcp.analysis.prescription_shape.
            bookend_minutes_from_steps`. Recorded at registration time so
            ``reconcile_prescriptions`` judges a hand-built quality session
            against its real bookends instead of the constant (Issue #1087).
        structure: The steps of a hand-built registered workout (Issue
            #1401), validated like a saved row's ``structure`` and stored as
            JSON so the run is judged against what the watch was asked to do.
        db_path: Path to DuckDB database. If None, uses the default path.

    Returns:
        ``True`` when a row was updated, ``False`` when the id does not exist.

    Raises:
        ValueError: When ``status`` is not a known lifecycle state or
            ``structure`` is invalid.
    """
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(ALLOWED_STATUSES)}, got {status!r}"
        )
    if structure is not None:
        from garmin_mcp.analysis.workout_structure import validate_structure

        validate_structure(structure, title="registered workout")

    if db_path is None:
        db_path = _default_db_path()

    from garmin_mcp.database.connection import get_write_connection

    assignments = ["status = ?", "updated_at = now()"]
    params: list[Any] = [status]
    if garmin_workout_id is not None:
        assignments.append("garmin_workout_id = ?")
        params.append(garmin_workout_id)
    if garmin_schedule_id is not None:
        assignments.append("garmin_schedule_id = ?")
        params.append(garmin_schedule_id)
    if actual_activity_id is not None:
        assignments.append("actual_activity_id = ?")
        params.append(actual_activity_id)
    if registered_bookend_minutes is not None:
        assignments.append("registered_bookend_minutes = ?")
        params.append(registered_bookend_minutes)
    if structure is not None:
        assignments.append("structure = ?")
        params.append(_json_or_none(structure))
    params.append(prescription_id)

    with get_write_connection(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM weekly_prescriptions WHERE prescription_id = ?",
            [prescription_id],
        ).fetchone()
        if exists is None:
            # No id in the log line: CodeQL flags anything named "prescription"
            # as private data (py/clear-text-logging-sensitive-data). The caller
            # gets False and already knows which id it asked for.
            logger.warning("Prescription row not found; no status update")
            return False

        conn.execute(
            f"UPDATE weekly_prescriptions SET {', '.join(assignments)} "
            "WHERE prescription_id = ?",
            params,
        )

    return True
