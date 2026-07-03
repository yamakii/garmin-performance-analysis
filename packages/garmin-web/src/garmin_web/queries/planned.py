"""Read-only queries for the planned_workouts table (Issue #721).

Backs the Today dashboard's "今日の予定 vs 実績" card: returns the planned
session scheduled for a given day so the Web layer can contrast it with the
day's actual activity. Read-only — plan generation is owned by the CLI
(`/plan-training`). Multiple plan versions may exist per date (migration
`add_plan_versioning`), so the latest version wins.
"""

import datetime as _dt

import duckdb

# Fields the Today card needs; ``version`` is only used for latest-version
# selection and is not returned.
_PLANNED_COLUMNS = (
    "workout_id, workout_type, description_ja, target_hr_low, target_hr_high, "
    "target_pace_low, target_pace_high, target_distance_km, "
    "actual_activity_id, adherence_score"
)

# One row for the date: the highest version wins when a plan has been
# re-generated (versions accumulate rather than overwrite).
_SELECT_FOR_DATE = f"""
    SELECT {_PLANNED_COLUMNS}
    FROM planned_workouts
    WHERE workout_date = ?
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY workout_date ORDER BY version DESC
    ) = 1
    LIMIT 1
"""


def get_planned_workout_for_date(
    conn: duckdb.DuckDBPyConnection, date: str
) -> dict | None:
    """Return the planned workout scheduled for ``date`` (latest version).

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        date: Target day (``YYYY-MM-DD``).

    Returns:
        A dict with ``workout_type``, ``description_ja``,
        ``target_hr_low``/``target_hr_high``, ``target_pace_low``/
        ``target_pace_high``, ``target_distance_km`` (plus ``workout_id``,
        ``actual_activity_id`` and ``adherence_score``), or ``None`` when no
        workout is planned for that day. Date/timestamp values are ``str``.
    """
    result = conn.execute(_SELECT_FOR_DATE, [date])
    row = result.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in result.description]
    record: dict = {}
    for col, value in zip(columns, row, strict=True):
        if isinstance(value, _dt.date | _dt.datetime):
            record[col] = str(value)
        else:
            record[col] = value
    return record
