"""Athlete profile DB inserter.

Persists the athlete's current focus, race goals, and season retrospectives as a
single profile object across three tables (``athlete_profile``,
``athlete_goals``, ``season_retrospectives``).

Write semantics:
- A save is a partial update: a profile key absent from the payload
  (``current_focus``, ``focus_notes``, ``week_start_day``, ``goals``,
  ``retrospectives``) keeps its stored value. A present key replaces the
  stored value, so ``None`` / ``[]`` still clears it (Issue #1468).
- ``athlete_profile`` is UPSERTed on ``user_id`` (the PK), refreshing
  ``updated_at`` on every save.
- ``athlete_goals`` and ``season_retrospectives`` are fully replaced per
  ``user_id`` (DELETE then INSERT) when their key is present, so each save
  reflects the supplied lists exactly without duplication.
- ``append_focus_notes`` appends text to ``focus_notes`` (at the end, or at
  the end of one ``【heading】`` section) without the caller resending the
  whole notes, leaving every other field untouched.
- ``athlete_profile_versions`` receives an append-only JSON snapshot of the
  whole (merged) profile on every write, so overwritten content (e.g. a
  compressed ``focus_notes``) stays recoverable as history.
- Surrogate keys are drawn from ``seq_athlete_goals_id`` /
  ``seq_season_retrospectives_id`` / ``seq_athlete_profile_versions_id`` via
  ``nextval``, mirroring the ``seq_section_analyses_id`` pattern in
  ``db_writer.py``.
- ``athlete_symptoms`` is append-only: every reported pain / niggle is a new
  row, so the same day can carry one row per body region and a later report
  never overwrites an earlier one.
- ``intake_confirmations`` is upserted on ``(user_id, date)``: the latest
  confirmation of a day's food log replaces the earlier one.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from garmin_mcp.validation.pictographs import reject_pictographs

logger = logging.getLogger(__name__)


_GOAL_FIELDS = (
    "race_name",
    "race_date",
    "priority",
    "goal_type",
    "distance_km",
    "target_time_seconds",
    "status",
    "notes",
)
_RETRO_FIELDS = (
    "season_label",
    "period_start",
    "period_end",
    "narrative",
    "key_learnings",
)
_PROFILE_KEYS = (
    "current_focus",
    "focus_notes",
    "week_start_day",
    "goals",
    "retrospectives",
)


def _load_stored_profile(conn: Any, user_id: str) -> dict[str, Any]:
    """Read the stored profile in the save-payload shape (empty when absent)."""
    row = conn.execute(
        "SELECT current_focus, focus_notes, week_start_day "
        "FROM athlete_profile WHERE user_id = ?",
        [user_id],
    ).fetchone()
    goal_rows = conn.execute(
        f"SELECT {', '.join(_GOAL_FIELDS)} FROM athlete_goals "
        "WHERE user_id = ? ORDER BY goal_id",
        [user_id],
    ).fetchall()
    retro_rows = conn.execute(
        f"SELECT {', '.join(_RETRO_FIELDS)} FROM season_retrospectives "
        "WHERE user_id = ? ORDER BY retro_id",
        [user_id],
    ).fetchall()
    return {
        "user_id": user_id,
        "current_focus": row[0] if row else None,
        "focus_notes": row[1] if row else None,
        "week_start_day": row[2] if row and row[2] is not None else 0,
        "goals": [dict(zip(_GOAL_FIELDS, r, strict=True)) for r in goal_rows],
        "retrospectives": [
            dict(zip(_RETRO_FIELDS, r, strict=True)) for r in retro_rows
        ],
    }


def _append_profile_version(conn: Any, user_id: str, profile: dict[str, Any]) -> int:
    """Append a JSON snapshot of the whole profile and return its version_id."""
    id_row = conn.execute(
        "SELECT nextval('seq_athlete_profile_versions_id')"
    ).fetchone()
    version_id = int(id_row[0]) if id_row is not None else 0
    # created_at is left to the table DEFAULT (CURRENT_TIMESTAMP).
    conn.execute(
        """
        INSERT INTO athlete_profile_versions (version_id, user_id, profile_data)
        VALUES (?, ?, ?)
        """,
        [version_id, user_id, json.dumps(profile, ensure_ascii=False, default=str)],
    )
    return version_id


def insert_athlete_profile(profile: dict[str, Any], db_path: str | None = None) -> None:
    """Insert (or update) an athlete profile with its goals and retrospectives.

    A save is a partial update: keys absent from ``profile`` keep their stored
    value, so a payload carrying only ``focus_notes`` does not wipe the goals,
    the retrospectives or ``current_focus``. A present key replaces the stored
    value (``None`` / ``[]`` clears it). The normalized tables keep the latest
    canonical state, and the merged profile is additionally appended to
    ``athlete_profile_versions`` as a JSON snapshot so every save is preserved
    as a new version.

    Args:
        profile: Profile dict with keys ``user_id`` (defaults to ``"default"``),
            ``current_focus``, ``focus_notes``, ``week_start_day`` (int,
            0=Monday … 6=Sunday; defaults to 0), ``goals`` (list of goal dicts),
            and ``retrospectives`` (list of retrospective dicts). Every key but
            ``user_id`` is optional and keeps its stored value when omitted.
        db_path: Path to DuckDB database. If None, uses default.

    Raises:
        ValueError: When the profile prose carries emoji (Issue #1428).
    """
    # The profile prose is shown on the web Goal page.
    reject_pictographs(
        {
            key: profile.get(key)
            for key in ("current_focus", "focus_notes", "goals", "retrospectives")
        },
        where="save_athlete_profile",
    )

    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = profile.get("user_id") or "default"

    with get_write_connection(db_path) as conn:
        # Omitted keys keep their stored value; present keys replace it.
        stored = _load_stored_profile(conn, user_id)
        merged: dict[str, Any] = {"user_id": user_id}
        for key in _PROFILE_KEYS:
            merged[key] = profile[key] if key in profile else stored[key]
        if merged["week_start_day"] is None:
            merged["week_start_day"] = 0
        merged["goals"] = merged["goals"] or []
        merged["retrospectives"] = merged["retrospectives"] or []

        # UPSERT the single-row profile (PK = user_id), refreshing updated_at.
        # updated_at uses the table DEFAULT (CURRENT_TIMESTAMP) on insert and is
        # refreshed via now() on conflict.
        conn.execute(
            """
            INSERT INTO athlete_profile (
                user_id, current_focus, focus_notes, week_start_day
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                current_focus = EXCLUDED.current_focus,
                focus_notes = EXCLUDED.focus_notes,
                week_start_day = EXCLUDED.week_start_day,
                updated_at = now()
            """,
            [
                user_id,
                merged["current_focus"],
                merged["focus_notes"],
                merged["week_start_day"],
            ],
        )

        # Replace goals for this user_id (DELETE then INSERT), only when the
        # payload carries them; an omitted key leaves the stored goals as is.
        if "goals" in profile:
            conn.execute("DELETE FROM athlete_goals WHERE user_id = ?", [user_id])
            for goal in merged["goals"]:
                conn.execute(
                    """
                    INSERT INTO athlete_goals (
                        goal_id, user_id, race_name, race_date, priority,
                        goal_type, distance_km, target_time_seconds, status, notes
                    ) VALUES (
                        nextval('seq_athlete_goals_id'), ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    [
                        user_id,
                        goal.get("race_name"),
                        goal.get("race_date"),
                        goal.get("priority"),
                        goal.get("goal_type"),
                        goal.get("distance_km"),
                        goal.get("target_time_seconds"),
                        goal.get("status", "active"),
                        goal.get("notes"),
                    ],
                )

        # Replace retrospectives the same way.
        if "retrospectives" in profile:
            conn.execute(
                "DELETE FROM season_retrospectives WHERE user_id = ?", [user_id]
            )
            for retro in merged["retrospectives"]:
                conn.execute(
                    """
                    INSERT INTO season_retrospectives (
                        retro_id, user_id, season_label, period_start, period_end,
                        narrative, key_learnings
                    ) VALUES (
                        nextval('seq_season_retrospectives_id'), ?, ?, ?, ?, ?, ?
                    )
                    """,
                    [
                        user_id,
                        retro.get("season_label"),
                        retro.get("period_start"),
                        retro.get("period_end"),
                        retro.get("narrative"),
                        retro.get("key_learnings"),
                    ],
                )

        # Append an immutable snapshot of the whole merged profile.
        _append_profile_version(conn, user_id, merged)

        logger.info(
            "Saved athlete profile user_id=%s (%d goals, %d retrospectives)",
            user_id,
            len(merged["goals"]),
            len(merged["retrospectives"]),
        )


# A line-start ``【`` opens a section; an inline ``（【…】参照）`` does not.
_LINE_HEADING_RE = re.compile(r"(?m)^【")
_SECTION_BODY_TRAILING = "\n\r \t　"


def _section_heading_re(section: str) -> re.Pattern[str]:
    """Match a line-start ``【section】`` or ``【section: …】`` heading."""
    return re.compile(rf"(?m)^【{re.escape(section)}(?:】|[:：][^】\n]*】)")


def _append_to_notes(notes: str, text: str, section: str | None) -> tuple[str, bool]:
    """Return ``(new focus_notes, section_created)`` after appending ``text``."""
    if section is None:
        return (f"{notes}\n{text}" if notes else text), False

    matches = list(_section_heading_re(section).finditer(notes))
    if len(matches) > 1:
        raise ValueError(
            f"append_focus_notes: section {section!r} matches {len(matches)} "
            "headings; refusing an ambiguous append"
        )
    if not matches:
        line = f"【{section}】{text}"
        return (f"{notes}\n{line}" if notes else line), True

    heading_end = matches[0].end()
    next_heading = _LINE_HEADING_RE.search(notes, heading_end)
    body_end = next_heading.start() if next_heading else len(notes)
    # Drop the newline (and stray spaces) before the next heading.
    while body_end > heading_end and notes[body_end - 1] in _SECTION_BODY_TRAILING:
        body_end -= 1
    body = notes[heading_end:body_end]
    joiner = "" if not body or body.endswith("。") else "。"
    return notes[:body_end] + joiner + text + notes[body_end:], False


def append_focus_notes(
    text: str,
    section: str | None = None,
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Append text to ``focus_notes`` without resending the whole notes.

    Reads the stored notes, appends ``text`` and writes back only the
    ``focus_notes`` column inside one write transaction, so ``current_focus``,
    ``week_start_day``, the goals and the retrospectives are never touched.
    The merged profile is appended to ``athlete_profile_versions`` like any
    other save (Issue #1468).

    Args:
        text: Text to append.
        section: Heading name of a ``【…】`` section. ``None`` appends ``text``
            as a new line at the end. When exactly one line-start heading is
            ``【section】`` or ``【section: …】``, ``text`` is appended to the
            end of that section's body (a ``。`` is added first when the body
            does not end with one, and no newline is inserted, so a section
            stays one line). When none matches, a new ``【section】text`` line
            is added at the end.
        user_id: Profile owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        ``{status, user_id, section, section_created, chars_before,
        chars_after, version_id}``.

    Raises:
        ValueError: When ``text`` is blank or carries emoji, or when
            ``section`` matches more than one heading.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("append_focus_notes: text must not be empty")
    if section is not None:
        section = section.strip().strip("【】").strip() or None
    # The profile prose is shown on the web Goal page.
    reject_pictographs({"text": text, "section": section}, where="append_focus_notes")

    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = user_id or "default"

    with get_write_connection(db_path) as conn:
        stored = _load_stored_profile(conn, user_id)
        notes = stored["focus_notes"] or ""
        new_notes, section_created = _append_to_notes(notes, text, section)

        # Only focus_notes changes; the other columns keep their stored value.
        conn.execute(
            """
            INSERT INTO athlete_profile (user_id, focus_notes, week_start_day)
            VALUES (?, ?, 0)
            ON CONFLICT (user_id) DO UPDATE SET
                focus_notes = EXCLUDED.focus_notes,
                updated_at = now()
            """,
            [user_id, new_notes],
        )

        stored["focus_notes"] = new_notes
        version_id = _append_profile_version(conn, user_id, stored)

        logger.info(
            "Appended focus_notes user_id=%s section=%s (%d -> %d chars)",
            user_id,
            section,
            len(notes),
            len(new_notes),
        )

    return {
        "status": "saved",
        "user_id": user_id,
        "section": section,
        "section_created": section_created,
        "chars_before": len(notes),
        "chars_after": len(new_notes),
        "version_id": version_id,
    }


def insert_weekly_review(review: dict[str, Any], db_path: str | None = None) -> int:
    """Insert a weekly review record, appending a new version (no overwrite).

    Every save inserts a fresh row: re-saving the same
    ``(user_id, week_start_date)`` appends a new version rather than overwriting
    the prior one, preserving the full review history. The reader returns the
    latest version (highest ``created_at``) per week as canonical. The free-form
    ``review_data`` payload is serialized to JSON and stored as a VARCHAR column.
    Surrogate keys are drawn from ``seq_weekly_reviews_id`` via ``nextval`` and
    ``created_at`` is left to the table DEFAULT (``CURRENT_TIMESTAMP``).

    The generated ``review_id`` is returned so the caller can link the weekly
    prescriptions it saves next to this exact review version (Issue #980).

    The per-day plan does **not** belong here: the prescribed sessions with
    their rating and comment live in ``weekly_prescriptions`` alone, and the
    readers derive ``review_data.verdict`` from that batch at read time. A
    payload that still carries its own ``verdict`` rows is rejected so the two
    stores cannot drift again (Issue #1021).

    Args:
        review: Review dict with keys ``user_id`` (defaults to ``"default"``),
            ``week_start_date``, ``week_end_date``, ``review_date``,
            ``review_data`` (dict, serialized to JSON), ``agent_name``, and
            ``agent_version``.
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        The new row's ``review_id``.

    Raises:
        ValueError: When ``review_data.verdict`` is non-empty, or when the
            prose carries emoji (Issue #1428).
    """
    review_data = review.get("review_data")
    if isinstance(review_data, dict) and review_data.get("verdict"):
        raise ValueError(
            "per-day plan rows belong in save_weekly_prescriptions "
            "(rating/rationale); verdict is derived"
        )
    # The review prose is rendered by the web app.
    reject_pictographs(review_data, where="save_weekly_review")

    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = review.get("user_id") or "default"
    review_data_json = json.dumps(review.get("review_data"), ensure_ascii=False)

    with get_write_connection(db_path) as conn:
        # Draw the surrogate key first so it can be returned to the caller.
        id_row = conn.execute("SELECT nextval('seq_weekly_reviews_id')").fetchone()
        review_id = int(id_row[0]) if id_row is not None else 0

        # Always INSERT a new version; same-week re-saves append rather than
        # overwrite. created_at is left to the table DEFAULT (CURRENT_TIMESTAMP).
        conn.execute(
            """
            INSERT INTO weekly_reviews (
                review_id, user_id, week_start_date, week_end_date,
                review_date, review_data, agent_name, agent_version
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                review_id,
                user_id,
                review.get("week_start_date"),
                review.get("week_end_date"),
                review.get("review_date"),
                review_data_json,
                review.get("agent_name"),
                review.get("agent_version"),
            ],
        )

        logger.info(
            "Saved weekly review user_id=%s week_start_date=%s (review_id=%d)",
            user_id,
            review.get("week_start_date"),
            review_id,
        )

    return review_id


def insert_symptom(row: dict[str, Any], db_path: str | None = None) -> int:
    """Append one symptom report (pain / tightness) to ``athlete_symptoms``.

    Rows are append-only and one report covers one body region, so a day with
    two sore spots is two rows. A ``severity`` of 0 is stored like any other:
    it records that the question was asked and the answer was "clear", which a
    gate needs in order to tell "no pain" from "never asked" (issue #1220).

    Args:
        row: Symptom dict with keys ``user_id`` (defaults to ``"default"``),
            ``date`` (``YYYY-MM-DD``), ``body_region``, ``severity`` (0-10),
            ``phase``, and the optional ``side`` / ``activity_id`` / ``note``.
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        The new row's ``symptom_id``.

    Raises:
        ValueError: When ``note`` carries emoji (Issue #1428).
    """
    reject_pictographs(row.get("note"), where="save_symptom")

    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = row.get("user_id") or "default"

    with get_write_connection(db_path) as conn:
        # Draw the surrogate key first so it can be returned to the caller.
        id_row = conn.execute("SELECT nextval('athlete_symptoms_seq')").fetchone()
        symptom_id = int(id_row[0]) if id_row is not None else 0

        # created_at is left to the table DEFAULT (current_timestamp).
        conn.execute(
            """
            INSERT INTO athlete_symptoms (
                symptom_id, user_id, date, body_region, side,
                severity, phase, activity_id, note
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                symptom_id,
                user_id,
                row.get("date"),
                row.get("body_region"),
                row.get("side"),
                row.get("severity"),
                row.get("phase"),
                row.get("activity_id"),
                row.get("note"),
            ],
        )

        logger.info(
            "Saved symptom user_id=%s date=%s region=%s severity=%s (symptom_id=%d)",
            user_id,
            row.get("date"),
            row.get("body_region"),
            row.get("severity"),
            symptom_id,
        )

    return symptom_id


_INTAKE_CONFIRMATION_STATUSES = frozenset({"complete", "incomplete"})


def insert_intake_confirmation(
    date: str,
    status: str,
    note: str | None = None,
    user_id: str = "default",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Upsert the athlete's confirmation of one day's intake log.

    One row per ``(user_id, date)``: a second confirmation for the same day
    replaces the first, and ``confirmed_at`` is refreshed to the local time of
    the save (the same naive-local convention as ``daily_energy.fetched_at``,
    so the reader can tell whether the intake changed afterwards). Issue #1434.

    Args:
        date: Day the confirmation is about (``YYYY-MM-DD``).
        status: ``"complete"`` (the log holds everything eaten) or
            ``"incomplete"`` (food is missing; the day is excluded).
        note: Optional free-form note in the athlete's own words.
        user_id: Profile owner identifier (defaults to ``"default"``).
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        ``{"date", "status", "note", "user_id", "confirmed_at"}``.

    Raises:
        ValueError: When ``status`` is not ``complete`` / ``incomplete`` or
            ``note`` carries emoji (Issue #1428).
    """
    from datetime import date as date_cls
    from datetime import datetime

    if status not in _INTAKE_CONFIRMATION_STATUSES:
        raise ValueError(
            f"save_intake_confirmation: status must be 'complete' or "
            f"'incomplete', got {status!r}"
        )
    date_cls.fromisoformat(date)
    reject_pictographs(note, where="save_intake_confirmation")

    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = user_id or "default"
    confirmed_at = datetime.now().replace(microsecond=0)

    with get_write_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO intake_confirmations (
                user_id, date, status, note, confirmed_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, date) DO UPDATE SET
                status = EXCLUDED.status,
                note = EXCLUDED.note,
                confirmed_at = EXCLUDED.confirmed_at
            """,
            [user_id, date, status, note, confirmed_at],
        )
        logger.info(
            "Saved intake confirmation user_id=%s date=%s status=%s",
            user_id,
            date,
            status,
        )

    return {
        "date": date,
        "status": status,
        "note": note,
        "user_id": user_id,
        "confirmed_at": confirmed_at.isoformat(),
    }
