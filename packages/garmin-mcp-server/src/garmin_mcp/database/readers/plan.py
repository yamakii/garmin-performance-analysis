"""Training plan ledger DB reader.

Reads the mesocycle ledger (``training_blocks`` / ``training_block_versions``)
and the structured weekly prescriptions (``weekly_prescriptions``).

Two conventions apply throughout:

- JSON columns (``quality_types``, ``long_run_ladder``, ``cutback_rule``) are
  decoded back into lists/dicts, and every ``date`` / ``TIMESTAMP`` value is
  converted to ``str`` so results are directly ``json.dumps``-able by MCP tools.
- ``weekly_prescriptions`` is append-only per ``batch_id``: the highest
  ``batch_id`` for a week is canonical and superseded batches are never
  returned.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.utils.week import get_week_start_day, week_start

logger = logging.getLogger(__name__)

_BLOCK_COLUMNS = (
    "block_id, user_id, sequence, phase, title, start_date, end_date, purpose, "
    "weight_mode, quality_sessions_per_week, quality_types, long_run_ladder, "
    "cutback_rule, notes, created_at"
)

_BLOCK_JSON_COLUMNS = ("quality_types", "long_run_ladder", "cutback_rule")

_PRESCRIPTION_COLUMN_NAMES = (
    "prescription_id",
    "batch_id",
    "user_id",
    "review_id",
    "week_start_date",
    "date",
    "session_type",
    "title",
    "target_minutes",
    "target_km",
    "hr_low",
    "hr_high",
    "pace_low_s_per_km",
    "pace_high_s_per_km",
    "rationale",
    "status",
    "garmin_workout_id",
    "garmin_schedule_id",
    "actual_activity_id",
    "created_at",
    "updated_at",
)

_PRESCRIPTION_COLUMNS = ", ".join(_PRESCRIPTION_COLUMN_NAMES)

# Qualified variant for the join in ``list_prescriptions`` (``week_start_date``
# and ``batch_id`` exist on both sides, so unqualified names are ambiguous).
_PRESCRIPTION_COLUMNS_QUALIFIED = ", ".join(
    f"p.{name}" for name in _PRESCRIPTION_COLUMN_NAMES
)


class PlanReader(BaseDBReader):
    """Reads the training block ledger and weekly prescriptions from DuckDB."""

    # ------------------------------------------------------------------
    # training_blocks
    # ------------------------------------------------------------------

    def get_training_blocks(self, user_id: str = "default") -> list[dict[str, Any]]:
        """Get all training blocks for a user in display order.

        Args:
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            Blocks ordered by ``sequence``, with ``quality_types`` /
            ``long_run_ladder`` / ``cutback_rule`` JSON-decoded and dates
            converted to ``str``. Empty when no block is registered.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_BLOCK_COLUMNS} FROM training_blocks "
                "WHERE user_id = ? ORDER BY sequence, block_id",
                [user_id],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [_block_row_to_dict(columns, row) for row in rows]

    def get_block_for_date(
        self, on_date: str, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """Get the block whose date range covers ``on_date``.

        Args:
            on_date: Date within the block (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            The covering block (lowest ``sequence`` wins when ranges overlap),
            or ``None`` when no block covers the date.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                f"SELECT {_BLOCK_COLUMNS} FROM training_blocks "
                "WHERE user_id = ? AND start_date <= CAST(? AS DATE) "
                "AND end_date >= CAST(? AS DATE) "
                "ORDER BY sequence, block_id LIMIT 1",
                [user_id, on_date, on_date],
            ).fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in conn.description]
            return _block_row_to_dict(columns, row)

    def get_ladder_step_for_week(
        self, week_start_date: str, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """Get the long-run ladder step for a week with its neighbours.

        Args:
            week_start_date: Week start (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            ``{"current": step|None, "previous": step|None, "next": step|None}``
            derived from the ladder of the block covering the week, or ``None``
            when no block covers ``week_start_date``. ``current`` is ``None``
            when the block's ladder has no step for that exact week, in which
            case ``previous`` / ``next`` are the nearest surrounding steps.
        """
        block = self.get_block_for_date(week_start_date, user_id=user_id)
        if block is None:
            return None

        ladder = block.get("long_run_ladder") or []
        steps = sorted(
            (s for s in ladder if isinstance(s, dict) and s.get("week_start")),
            key=lambda s: str(s["week_start"]),
        )

        current: dict[str, Any] | None = None
        previous: dict[str, Any] | None = None
        next_step: dict[str, Any] | None = None
        for index, step in enumerate(steps):
            if str(step["week_start"]) == week_start_date:
                current = step
                previous = steps[index - 1] if index > 0 else None
                next_step = steps[index + 1] if index + 1 < len(steps) else None
                break
        else:
            for step in steps:
                if str(step["week_start"]) < week_start_date:
                    previous = step
                elif next_step is None:
                    next_step = step

        return {"current": current, "previous": previous, "next": next_step}

    def list_training_block_versions(
        self, user_id: str = "default", limit: int = 5
    ) -> list[dict[str, Any]]:
        """List recent block-list snapshots (metadata only), newest first.

        Every ``save_training_blocks`` replaces the canonical rows and appends a
        snapshot of the whole list here, so this exposes the overwritten history
        as a lightweight index rather than returning the payloads.

        Args:
            user_id: Ledger owner identifier (defaults to ``"default"``).
            limit: Maximum number of versions to return (default 5).

        Returns:
            ``{version_id, user_id, created_at, n_blocks, titles}`` dicts
            ordered ``created_at`` DESC (ties broken by ``version_id`` DESC).
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT version_id, user_id, created_at, blocks_data "
                "FROM training_block_versions WHERE user_id = ? "
                "ORDER BY created_at DESC, version_id DESC LIMIT ?",
                [user_id, limit],
            ).fetchall()
        return [_block_version_summary(row) for row in rows]

    # ------------------------------------------------------------------
    # weekly_prescriptions
    # ------------------------------------------------------------------

    def resolve_week_start(self, on_date: str, user_id: str = "default") -> str:
        """Return the start date of the week containing ``on_date``.

        Uses the athlete's configured ``week_start_day`` (``athlete_profile``,
        Monday when unset) so every plan feature maps a day to the same week the
        weekly review used.

        Args:
            on_date: Date (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            The containing week's start date as ``YYYY-MM-DD``.
        """
        day = _dt.datetime.strptime(on_date, "%Y-%m-%d").date()
        with self._get_connection() as conn:
            start_day = get_week_start_day(conn, user_id)
        return week_start(day, start_day).isoformat()

    def get_weekly_prescriptions(
        self, week_start_date: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Get the canonical (latest batch) prescriptions for one week.

        Args:
            week_start_date: Week start (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            Rows of the highest ``batch_id`` for that week ordered by ``date``.
            Empty when the week has no prescriptions.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_PRESCRIPTION_COLUMNS} FROM weekly_prescriptions "
                "WHERE user_id = ? AND week_start_date = CAST(? AS DATE) "
                "AND batch_id = ("
                "  SELECT MAX(batch_id) FROM weekly_prescriptions "
                "  WHERE user_id = ? AND week_start_date = CAST(? AS DATE)"
                ") ORDER BY date, prescription_id",
                [user_id, week_start_date, user_id, week_start_date],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [_row_to_dict(columns, row) for row in rows]

    def get_prescriptions_for_date(
        self, on_date: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Get the canonical prescriptions for a single day.

        The containing week is resolved with the athlete's configured
        ``week_start_day`` (``athlete_profile``), so the day maps to the same
        week the weekly review used.

        Args:
            on_date: Date (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            Latest-batch rows for that date (usually 0 or 1). Empty when the day
            has no prescription.
        """
        containing_week = self.resolve_week_start(on_date, user_id=user_id)
        return [
            row
            for row in self.get_weekly_prescriptions(containing_week, user_id=user_id)
            if row.get("date") == on_date
        ]

    def list_prescriptions(
        self, start_date: str, end_date: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Get canonical prescriptions across every week overlapping a range.

        The latest batch is resolved per week *before* the date filter, so a
        week whose newest batch has no row inside the range never falls back to
        a superseded batch.

        Args:
            start_date: Inclusive range start (``YYYY-MM-DD``).
            end_date: Inclusive range end (``YYYY-MM-DD``).
            user_id: Ledger owner identifier (defaults to ``"default"``).

        Returns:
            Latest-batch rows with ``date`` inside the range, ordered by
            ``date``. Empty when nothing matches.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "WITH latest AS ("
                "  SELECT week_start_date, MAX(batch_id) AS batch_id "
                "  FROM weekly_prescriptions WHERE user_id = ? "
                "  GROUP BY week_start_date"
                ") "
                f"SELECT {_PRESCRIPTION_COLUMNS_QUALIFIED} "
                "FROM weekly_prescriptions p "
                "JOIN latest l ON p.week_start_date = l.week_start_date "
                "AND p.batch_id = l.batch_id "
                "WHERE p.user_id = ? "
                "AND p.date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) "
                "ORDER BY p.date, p.prescription_id",
                [user_id, user_id, start_date, end_date],
            ).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [_row_to_dict(columns, row) for row in rows]


def _row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    """Zip a row into a dict, converting date/datetime values to str."""
    record: dict[str, Any] = {}
    for col, value in zip(columns, row, strict=False):
        if isinstance(value, _dt.date | _dt.datetime):
            record[col] = str(value)
        else:
            record[col] = value
    return record


def _block_row_to_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    """Convert a training_blocks row, JSON-decoding its structured columns."""
    record = _row_to_dict(columns, row)
    for col in _BLOCK_JSON_COLUMNS:
        raw = record.get(col)
        record[col] = json.loads(raw) if isinstance(raw, str) else None
    return record


def _block_version_summary(row: tuple) -> dict[str, Any]:
    """Summarize a ``(version_id, user_id, created_at, blocks_data)`` row.

    The snapshot is decoded only to derive size/shape hints; sparse or
    unexpected payloads degrade to ``0``/``[]`` instead of raising.
    """
    version_id, user_id, created_at, raw = row
    snapshot = json.loads(raw) if raw is not None else None
    if not isinstance(snapshot, list):
        snapshot = []
    return {
        "version_id": version_id,
        "user_id": user_id,
        "created_at": str(created_at) if created_at is not None else None,
        "n_blocks": len(snapshot),
        "titles": [
            b.get("title") for b in snapshot if isinstance(b, dict) and b.get("title")
        ],
    }
