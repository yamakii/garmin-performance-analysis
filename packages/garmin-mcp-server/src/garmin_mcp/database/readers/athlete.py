"""Athlete profile DB reader."""

from __future__ import annotations

import json
import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class AthleteReader(BaseDBReader):
    """Reads the athlete profile (focus + goals + retrospectives) from DuckDB."""

    def get_athlete_profile(self, user_id: str = "default") -> dict[str, Any]:
        """Get the merged athlete profile for a user.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            Dict with ``user_id``, ``current_focus``, ``focus_notes``,
            ``week_start_day`` (int, 0=Monday … 6=Sunday), ``updated_at`` (str),
            ``goals`` (list) and ``retrospectives`` (list). When no profile row
            exists, ``current_focus``/``focus_notes``/``updated_at`` are ``None``,
            ``week_start_day`` is ``0`` and the lists are empty. All
            date/timestamp values are converted to ``str``.
        """
        with self._get_connection() as conn:
            profile_row = conn.execute(
                "SELECT current_focus, focus_notes, week_start_day, updated_at "
                "FROM athlete_profile WHERE user_id = ?",
                [user_id],
            ).fetchone()

            if profile_row is None:
                result: dict[str, Any] = {
                    "user_id": user_id,
                    "current_focus": None,
                    "focus_notes": None,
                    "week_start_day": 0,
                    "updated_at": None,
                }
            else:
                result = {
                    "user_id": user_id,
                    "current_focus": profile_row[0],
                    "focus_notes": profile_row[1],
                    "week_start_day": (
                        profile_row[2] if profile_row[2] is not None else 0
                    ),
                    "updated_at": (
                        str(profile_row[3]) if profile_row[3] is not None else None
                    ),
                }

            goal_rows = conn.execute(
                "SELECT goal_id, race_name, race_date, priority, goal_type, "
                "distance_km, target_time_seconds, status, notes "
                "FROM athlete_goals WHERE user_id = ? ORDER BY goal_id",
                [user_id],
            ).fetchall()
            goal_columns = [desc[0] for desc in conn.description]
            result["goals"] = [
                self._row_to_dict(goal_columns, row) for row in goal_rows
            ]

            retro_rows = conn.execute(
                "SELECT retro_id, season_label, period_start, period_end, "
                "narrative, key_learnings "
                "FROM season_retrospectives WHERE user_id = ? ORDER BY retro_id",
                [user_id],
            ).fetchall()
            retro_columns = [desc[0] for desc in conn.description]
            result["retrospectives"] = [
                self._row_to_dict(retro_columns, row) for row in retro_rows
            ]

            return result

    def list_athlete_profile_versions(
        self, user_id: str = "default", limit: int = 5
    ) -> list[dict[str, Any]]:
        """List recent athlete profile snapshots (metadata only), newest first.

        Every ``save_athlete_profile`` appends a JSON snapshot of the whole
        profile to ``athlete_profile_versions``; the normalized tables keep the
        latest canonical state. This exposes the overwritten history as a
        lightweight index: the snapshots themselves are large (tens of thousands
        of characters), so ``profile_data`` is deliberately not returned here.
        Fetch one version in full via :meth:`get_athlete_profile_version`.

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``).
            limit: Maximum number of versions to return (default 5).

        Returns:
            A list of ``{version_id, user_id, created_at, current_focus,
            focus_notes_chars, n_goals, n_retrospectives}`` dicts ordered
            ``created_at`` DESC (ties broken by ``version_id`` DESC).
            ``created_at`` is converted to ``str``; the summary fields are
            derived from the decoded snapshot and fall back to ``0``/``None``
            when a key is missing. Empty when no version exists.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT version_id, user_id, created_at, profile_data "
                "FROM athlete_profile_versions WHERE user_id = ? "
                "ORDER BY created_at DESC, version_id DESC LIMIT ?",
                [user_id, limit],
            ).fetchall()
            return [self._profile_version_summary(row) for row in rows]

    def get_athlete_profile_version(
        self, version_id: int, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """Get one athlete profile snapshot in full.

        Args:
            version_id: Version identifier from
                :meth:`list_athlete_profile_versions`.
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            ``{version_id, user_id, created_at, profile_data}`` where
            ``profile_data`` is the snapshot JSON-decoded back into a dict and
            ``created_at`` is converted to ``str``, or ``None`` when no such
            version exists for the user.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT version_id, user_id, created_at, profile_data "
                "FROM athlete_profile_versions "
                "WHERE version_id = ? AND user_id = ?",
                [version_id, user_id],
            ).fetchone()

            if row is None:
                return None

            columns = [desc[0] for desc in conn.description]
            return self._profile_version_row_to_dict(columns, row)

    def get_weekly_review(
        self, week_start_date: str | None = None, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """Get the latest version of a single weekly review record.

        Weekly reviews are versioned: each save appends a new row, so a given
        week may have several rows. This returns the latest version (highest
        ``created_at``).

        Args:
            week_start_date: Week start (``YYYY-MM-DD``). When ``None``, the
                latest version of the most recent week (highest
                ``week_start_date``) is returned.
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            A dict with the review columns (date/timestamp values converted to
            ``str``) where ``review_data`` is JSON-decoded back into a dict, or
            ``None`` when no matching review exists.
        """
        with self._get_connection() as conn:
            select_cols = (
                "review_id, user_id, week_start_date, week_end_date, review_date, "
                "review_data, created_at, agent_name, agent_version "
                "FROM weekly_reviews WHERE user_id = ?"
            )
            if week_start_date is None:
                row = conn.execute(
                    f"SELECT {select_cols} "
                    "ORDER BY week_start_date DESC, created_at DESC LIMIT 1",
                    [user_id],
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT {select_cols} AND week_start_date = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    [user_id, week_start_date],
                ).fetchone()

            if row is None:
                return None

            columns = [desc[0] for desc in conn.description]
            return self._review_row_to_dict(columns, row)

    def list_weekly_reviews(
        self, limit: int = 8, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """List recent weekly reviews (latest version per week) in week order.

        Weekly reviews are versioned (multiple rows per week). This deduplicates
        to the latest version per week before applying the limit.

        Args:
            limit: Maximum number of reviews to return (default 8).
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            A list of review dicts (newest week first, latest version per week).
            Each ``review_data`` is JSON-decoded back into a dict.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT review_id, user_id, week_start_date, week_end_date, "
                "review_date, review_data, created_at, agent_name, agent_version "
                "FROM weekly_reviews WHERE user_id = ? "
                "QUALIFY ROW_NUMBER() OVER ("
                "PARTITION BY week_start_date ORDER BY created_at DESC) = 1 "
                "ORDER BY week_start_date DESC LIMIT ?",
                [user_id, limit],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [self._review_row_to_dict(columns, row) for row in rows]

    def list_weekly_review_versions(
        self, week_start_date: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """List all versions of a weekly review for a given week.

        Args:
            week_start_date: Week start (``YYYY-MM-DD``).
            user_id: Profile owner identifier (defaults to ``"default"``).

        Returns:
            A list of every version saved for the week, newest first
            (``created_at`` DESC). Each ``review_data`` is JSON-decoded back into
            a dict. Empty when no review exists for the week.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT review_id, user_id, week_start_date, week_end_date, "
                "review_date, review_data, created_at, agent_name, agent_version "
                "FROM weekly_reviews WHERE user_id = ? AND week_start_date = ? "
                "ORDER BY created_at DESC",
                [user_id, week_start_date],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [self._review_row_to_dict(columns, row) for row in rows]

    @classmethod
    def _profile_version_row_to_dict(
        cls, columns: list[str], row: tuple
    ) -> dict[str, Any]:
        """Convert an athlete_profile_versions row, JSON-decoding the snapshot."""
        record = cls._row_to_dict(columns, row)
        raw = record.get("profile_data")
        record["profile_data"] = json.loads(raw) if raw is not None else None
        return record

    @classmethod
    def _profile_version_summary(cls, row: tuple) -> dict[str, Any]:
        """Summarize a ``(version_id, user_id, created_at, profile_data)`` row.

        The snapshot is decoded only to derive size/shape hints; sparse or
        unexpected payloads degrade to ``0``/``None`` instead of raising.
        """
        version_id, user_id, created_at, raw = row
        snapshot = json.loads(raw) if raw is not None else None
        if not isinstance(snapshot, dict):
            snapshot = {}

        focus_notes = snapshot.get("focus_notes")
        goals = snapshot.get("goals")
        retrospectives = snapshot.get("retrospectives")

        return {
            "version_id": version_id,
            "user_id": user_id,
            "created_at": str(created_at) if created_at is not None else None,
            "current_focus": snapshot.get("current_focus"),
            "focus_notes_chars": (
                len(focus_notes) if isinstance(focus_notes, str) else 0
            ),
            "n_goals": len(goals) if isinstance(goals, list) else 0,
            "n_retrospectives": (
                len(retrospectives) if isinstance(retrospectives, list) else 0
            ),
        }

    @classmethod
    def _review_row_to_dict(cls, columns: list[str], row: tuple) -> dict[str, Any]:
        """Convert a weekly_reviews row, JSON-decoding ``review_data``."""
        record = cls._row_to_dict(columns, row)
        raw = record.get("review_data")
        record["review_data"] = json.loads(raw) if raw is not None else None
        return record

    @staticmethod
    def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
        """Zip a row into a dict, converting date/datetime values to str."""
        import datetime as _dt

        record: dict[str, Any] = {}
        for col, value in zip(columns, row, strict=False):
            if isinstance(value, _dt.date | _dt.datetime):
                record[col] = str(value)
            else:
                record[col] = value
        return record
