"""Migration: Add ``athlete_profile_versions`` (append-only profile snapshots).

``save_athlete_profile`` overwrites the canonical athlete profile (profile
UPSERT + goals/retrospectives DELETE→INSERT), so prior ``focus_notes`` content
was lost on every save. This migration adds an append-only snapshot table: each
save stores the whole profile as a JSON snapshot while the normalized tables
keep holding the latest canonical state (all readers are unchanged).

The migration also seeds the *current* profile as the first version (one row per
``user_id`` that already has an ``athlete_profile`` row), so the state from
before versioning was introduced is preserved as the start of the history.
Seeding runs only while ``athlete_profile_versions`` is empty, which keeps the
migration idempotent.

Like the other athlete tables, this table is not API-derived and is therefore
intentionally excluded from ``scripts/regenerate/validator.py:AVAILABLE_TABLES``.
"""

from __future__ import annotations

import json
from typing import Any

import duckdb


def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    """Return whether ``table`` exists in the connected database."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchall()
    return bool(rows)


def _to_jsonable(value: Any) -> Any:
    """Convert DuckDB date/timestamp values to ``str`` (JSON-safe)."""
    import datetime as _dt

    if isinstance(value, _dt.date | _dt.datetime):
        return str(value)
    return value


def _profile_snapshot(conn: duckdb.DuckDBPyConnection, user_id: str) -> dict[str, Any]:
    """Build the full profile snapshot for ``user_id`` (reader-shaped dict)."""
    profile_row = conn.execute(
        "SELECT current_focus, focus_notes, week_start_day, updated_at "
        "FROM athlete_profile WHERE user_id = ?",
        [user_id],
    ).fetchone()

    snapshot: dict[str, Any] = {
        "user_id": user_id,
        "current_focus": profile_row[0] if profile_row else None,
        "focus_notes": profile_row[1] if profile_row else None,
        "week_start_day": (
            profile_row[2] if profile_row and profile_row[2] is not None else 0
        ),
        "updated_at": _to_jsonable(profile_row[3]) if profile_row else None,
    }

    goal_rows = conn.execute(
        "SELECT goal_id, race_name, race_date, priority, goal_type, distance_km, "
        "target_time_seconds, status, notes "
        "FROM athlete_goals WHERE user_id = ? ORDER BY goal_id",
        [user_id],
    ).fetchall()
    goal_columns = [desc[0] for desc in conn.description]
    snapshot["goals"] = [
        {col: _to_jsonable(val) for col, val in zip(goal_columns, row, strict=False)}
        for row in goal_rows
    ]

    retro_rows = conn.execute(
        "SELECT retro_id, season_label, period_start, period_end, narrative, "
        "key_learnings "
        "FROM season_retrospectives WHERE user_id = ? ORDER BY retro_id",
        [user_id],
    ).fetchall()
    retro_columns = [desc[0] for desc in conn.description]
    snapshot["retrospectives"] = [
        {col: _to_jsonable(val) for col, val in zip(retro_columns, row, strict=False)}
        for row in retro_rows
    ]
    return snapshot


def _seed_existing_profiles(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed the current profile of every user as version 1 (once)."""
    if not _table_exists(conn, "athlete_profile"):
        return

    existing = conn.execute("SELECT COUNT(*) FROM athlete_profile_versions").fetchone()
    if existing is not None and existing[0] > 0:
        # Already seeded (or already carrying saved versions) — stay idempotent.
        return

    user_rows = conn.execute(
        "SELECT user_id FROM athlete_profile ORDER BY user_id"
    ).fetchall()
    for (user_id,) in user_rows:
        snapshot = _profile_snapshot(conn, user_id)
        conn.execute(
            """
            INSERT INTO athlete_profile_versions (version_id, user_id, profile_data)
            VALUES (nextval('seq_athlete_profile_versions_id'), ?, ?)
            """,
            [user_id, json.dumps(snapshot, ensure_ascii=False, default=str)],
        )


def add_athlete_profile_versions(conn: duckdb.DuckDBPyConnection) -> None:
    """Create ``athlete_profile_versions`` and seed the current profile."""
    conn.execute(
        "CREATE SEQUENCE IF NOT EXISTS seq_athlete_profile_versions_id START 1"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS athlete_profile_versions (
            version_id INTEGER PRIMARY KEY,
            user_id VARCHAR DEFAULT 'default',
            profile_data VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _seed_existing_profiles(conn)
