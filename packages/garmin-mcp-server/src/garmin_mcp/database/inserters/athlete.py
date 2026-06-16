"""Athlete profile DB inserter.

Persists the athlete's current focus, race goals, and season retrospectives as a
single profile object across three tables (``athlete_profile``,
``athlete_goals``, ``season_retrospectives``).

Write semantics:
- ``athlete_profile`` is UPSERTed on ``user_id`` (the PK), refreshing
  ``updated_at`` on every save.
- ``athlete_goals`` and ``season_retrospectives`` are fully replaced per
  ``user_id`` (DELETE then INSERT), so each save reflects the supplied lists
  exactly without duplication.
- Surrogate keys are drawn from ``seq_athlete_goals_id`` /
  ``seq_season_retrospectives_id`` via ``nextval``, mirroring the
  ``seq_section_analyses_id`` pattern in ``db_writer.py``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def insert_athlete_profile(profile: dict[str, Any], db_path: str | None = None) -> None:
    """Insert (or update) an athlete profile with its goals and retrospectives.

    Args:
        profile: Profile dict with keys ``user_id`` (defaults to ``"default"``),
            ``current_focus``, ``focus_notes``, ``goals`` (list of goal dicts),
            and ``retrospectives`` (list of retrospective dicts).
        db_path: Path to DuckDB database. If None, uses default.
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = profile.get("user_id") or "default"
    goals = profile.get("goals") or []
    retrospectives = profile.get("retrospectives") or []

    with get_write_connection(db_path) as conn:
        # UPSERT the single-row profile (PK = user_id), refreshing updated_at.
        # updated_at uses the table DEFAULT (CURRENT_TIMESTAMP) on insert and is
        # refreshed via now() on conflict.
        conn.execute(
            """
            INSERT INTO athlete_profile (user_id, current_focus, focus_notes)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                current_focus = EXCLUDED.current_focus,
                focus_notes = EXCLUDED.focus_notes,
                updated_at = now()
            """,
            [user_id, profile.get("current_focus"), profile.get("focus_notes")],
        )

        # Replace goals for this user_id (DELETE then INSERT).
        conn.execute("DELETE FROM athlete_goals WHERE user_id = ?", [user_id])
        for goal in goals:
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

        # Replace retrospectives for this user_id (DELETE then INSERT).
        conn.execute("DELETE FROM season_retrospectives WHERE user_id = ?", [user_id])
        for retro in retrospectives:
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

        logger.info(
            "Saved athlete profile user_id=%s (%d goals, %d retrospectives)",
            user_id,
            len(goals),
            len(retrospectives),
        )


def insert_weekly_review(review: dict[str, Any], db_path: str | None = None) -> bool:
    """Insert a weekly review record, appending a new version (no overwrite).

    Every save inserts a fresh row: re-saving the same
    ``(user_id, week_start_date)`` appends a new version rather than overwriting
    the prior one, preserving the full review history. The reader returns the
    latest version (highest ``created_at``) per week as canonical. The free-form
    ``review_data`` payload is serialized to JSON and stored as a VARCHAR column.
    Surrogate keys are drawn from ``seq_weekly_reviews_id`` via ``nextval`` and
    ``created_at`` is left to the table DEFAULT (``CURRENT_TIMESTAMP``).

    Args:
        review: Review dict with keys ``user_id`` (defaults to ``"default"``),
            ``week_start_date``, ``week_end_date``, ``review_date``,
            ``review_data`` (dict, serialized to JSON), ``agent_name``, and
            ``agent_version``.
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        ``True`` on success.
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = review.get("user_id") or "default"
    review_data_json = json.dumps(review.get("review_data"), ensure_ascii=False)

    with get_write_connection(db_path) as conn:
        # Always INSERT a new version; same-week re-saves append rather than
        # overwrite. created_at is left to the table DEFAULT (CURRENT_TIMESTAMP).
        conn.execute(
            """
            INSERT INTO weekly_reviews (
                review_id, user_id, week_start_date, week_end_date,
                review_date, review_data, agent_name, agent_version
            ) VALUES (
                nextval('seq_weekly_reviews_id'), ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
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
            "Saved weekly review user_id=%s week_start_date=%s",
            user_id,
            review.get("week_start_date"),
        )

    return True
