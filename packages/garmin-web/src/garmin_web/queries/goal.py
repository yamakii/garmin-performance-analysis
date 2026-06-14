"""Read-only queries for the athlete goal tables.

Reads the athlete's current focus, race goals, and season retrospectives from
the three athlete-centric tables (``athlete_profile``, ``athlete_goals``,
``season_retrospectives``). Registration/updates are owned by the CLI
(``/set-goal``); the Web app is display-only.
"""

import datetime as _dt

import duckdb

_SELECT_PROFILE = """
    SELECT current_focus, focus_notes, updated_at
    FROM athlete_profile
    WHERE user_id = ?
"""

_SELECT_GOALS = """
    SELECT
        goal_id,
        race_name,
        race_date,
        priority,
        goal_type,
        distance_km,
        target_time_seconds,
        status,
        notes
    FROM athlete_goals
    WHERE user_id = ?
    ORDER BY goal_id
"""

_SELECT_RETROSPECTIVES = """
    SELECT
        retro_id,
        season_label,
        period_start,
        period_end,
        narrative,
        key_learnings
    FROM season_retrospectives
    WHERE user_id = ?
    ORDER BY retro_id
"""


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    """Zip a row into a dict, converting date/datetime values to str."""
    record: dict = {}
    for col, value in zip(columns, row, strict=True):
        if isinstance(value, _dt.date | _dt.datetime):
            record[col] = str(value)
        else:
            record[col] = value
    return record


def get_goal(
    conn: duckdb.DuckDBPyConnection,
    user_id: str = "default",
) -> dict:
    """Get the athlete goal payload (profile + goals + retrospectives).

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        Dict shaped as::

            {
                "profile": {
                    "current_focus": str | None,
                    "focus_notes": str | None,
                    "updated_at": str | None,
                },
                "goals": [ {goal columns...}, ... ],
                "retrospectives": [ {retro columns...}, ... ],
            }

        When no profile row exists the profile fields are ``None`` and the
        lists are empty. All date/timestamp values are converted to ``str``.
    """
    profile_row = conn.execute(_SELECT_PROFILE, [user_id]).fetchone()
    if profile_row is None:
        profile: dict = {
            "current_focus": None,
            "focus_notes": None,
            "updated_at": None,
        }
    else:
        profile = {
            "current_focus": profile_row[0],
            "focus_notes": profile_row[1],
            "updated_at": (str(profile_row[2]) if profile_row[2] is not None else None),
        }

    goal_result = conn.execute(_SELECT_GOALS, [user_id])
    goal_columns = [desc[0] for desc in goal_result.description]
    goals = [_row_to_dict(goal_columns, row) for row in goal_result.fetchall()]

    retro_result = conn.execute(_SELECT_RETROSPECTIVES, [user_id])
    retro_columns = [desc[0] for desc in retro_result.description]
    retrospectives = [
        _row_to_dict(retro_columns, row) for row in retro_result.fetchall()
    ]

    return {
        "profile": profile,
        "goals": goals,
        "retrospectives": retrospectives,
    }
