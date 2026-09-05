"""Read-only queries for the monthly plan view (Issue #983).

Answers 「この1ヶ月どう積むか?」 by joining the three things a plan month is made
of into one calendar-shaped payload:

- the mesocycle ledger (``training_blocks``) — the bands above the grid;
- the structured weekly prescriptions (``weekly_prescriptions``) — what each day
  was supposed to be, with its lifecycle ``status``;
- the actual runs (``activities``) — what the day turned into.

Two conventions carry over from ``garmin_mcp.database.readers.plan``:
``weekly_prescriptions`` is append-only per ``batch_id`` (the highest batch of a
week is canonical, superseded batches are never returned) and every ``DATE`` is
converted to ``str`` so the result is JSON-serializable at the API boundary.

The grid range is the first week containing day 1 through the last week
containing the last day of the month, using the athlete's configured
``week_start_day`` (``queries.settings.get_week_start_day``) — so with a Monday
start the Sunday long run is the last column of every row.

Adherence counting is delegated to ``garmin_mcp.analysis.derivations``: the
weekly review and this page must never disagree about what "3/4 実施" means.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import json
import re
from typing import Any

import duckdb
from garmin_mcp.analysis.derivations import summarize_adherence
from garmin_mcp.utils.week import week_start

from garmin_web.queries.settings import get_week_start_day

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

_BLOCK_COLUMNS = (
    "block_id, user_id, sequence, phase, title, start_date, end_date, purpose, "
    "weight_mode, quality_sessions_per_week, quality_types, long_run_ladder, "
    "cutback_rule, notes"
)

_BLOCK_JSON_COLUMNS = ("quality_types", "long_run_ladder", "cutback_rule")

# The band strip needs the block's identity and its shape, not its prose.
_BAND_KEYS = (
    "block_id",
    "phase",
    "title",
    "start_date",
    "end_date",
    "weight_mode",
    "quality_sessions_per_week",
)

_PRESCRIPTION_KEYS = (
    "prescription_id",
    "session_type",
    "title",
    "target_km",
    "target_minutes",
    "hr_high",
    "status",
)

_ACTIVITY_KEYS = (
    "activity_id",
    "activity_name",
    "total_distance_km",
    "avg_pace_seconds_per_km",
    "avg_heart_rate",
)

# Latest batch per week resolved *before* the date filter, so a week whose
# newest batch has no row inside the range never falls back to a superseded one.
_SELECT_PRESCRIPTIONS = """
    WITH latest AS (
        SELECT week_start_date, MAX(batch_id) AS batch_id
        FROM weekly_prescriptions WHERE user_id = ?
        GROUP BY week_start_date
    )
    SELECT p.prescription_id, p.date, p.session_type, p.title, p.target_km,
           p.target_minutes, p.hr_high, p.status
    FROM weekly_prescriptions p
    JOIN latest l ON p.week_start_date = l.week_start_date
                 AND p.batch_id = l.batch_id
    WHERE p.user_id = ?
      AND p.date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    ORDER BY p.date, p.prescription_id
"""

_SELECT_ACTIVITIES = """
    SELECT activity_id, activity_date, activity_name, total_distance_km,
           avg_pace_seconds_per_km, avg_heart_rate
    FROM activities
    WHERE activity_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    ORDER BY activity_date, activity_id
"""

_SELECT_BLOCKS_OVERLAPPING = f"""
    SELECT {_BLOCK_COLUMNS}
    FROM training_blocks
    WHERE user_id = ?
      AND start_date <= CAST(? AS DATE)
      AND end_date >= CAST(? AS DATE)
    ORDER BY sequence, block_id
"""

_SELECT_ALL_BLOCKS = f"""
    SELECT {_BLOCK_COLUMNS}
    FROM training_blocks
    WHERE user_id = ?
    ORDER BY sequence, block_id
"""

_SELECT_REVIEW_WEEKS = """
    SELECT DISTINCT week_start_date
    FROM weekly_reviews
    WHERE user_id = ?
      AND week_start_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
"""


def _rows(
    conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    """Run a query and return dict rows, with date/timestamp values as ``str``.

    A missing table degrades to an empty list rather than a 500: the plan
    tables arrive with a migration (#977 / #980) and a DB that predates it
    should render an empty month, not an error page.
    """
    try:
        result = conn.execute(sql, params)
    except duckdb.CatalogException:
        return []
    columns = [desc[0] for desc in result.description]
    records: list[dict[str, Any]] = []
    for row in result.fetchall():
        record: dict[str, Any] = {}
        for col, value in zip(columns, row, strict=True):
            record[col] = (
                str(value) if isinstance(value, _dt.date | _dt.datetime) else value
            )
        records.append(record)
    return records


def _decode_block(record: dict[str, Any]) -> dict[str, Any]:
    """JSON-decode a training_blocks row's structured columns in place."""
    for col in _BLOCK_JSON_COLUMNS:
        raw = record.get(col)
        record[col] = json.loads(raw) if isinstance(raw, str) else None
    return record


def _parse_month(month: str) -> tuple[_dt.date, _dt.date]:
    """Return the first and last day of a ``YYYY-MM`` month.

    Raises:
        ValueError: when ``month`` is not a zero-padded ``YYYY-MM`` string.
    """
    match = _MONTH_RE.match(month or "")
    if match is None:
        raise ValueError(f"month must be formatted YYYY-MM, got {month!r}")
    year, mon = int(match.group(1)), int(match.group(2))
    last_day = calendar.monthrange(year, mon)[1]
    return _dt.date(year, mon, 1), _dt.date(year, mon, last_day)


def _ladder_step_for_week(
    blocks: list[dict[str, Any]], week_start_iso: str
) -> dict[str, Any] | None:
    """Return the long-run ladder step a block declares for ``week_start_iso``.

    The covering block is the lowest-``sequence`` one whose range contains the
    week start (blocks are pre-sorted). ``None`` when no block covers the week
    or its ladder has no step for that exact week.
    """
    for block in blocks:
        start, end = block.get("start_date"), block.get("end_date")
        if start is None or end is None:
            continue
        if not (str(start) <= week_start_iso <= str(end)):
            continue
        ladder = block.get("long_run_ladder") or []
        for step in ladder:
            if isinstance(step, dict) and str(step.get("week_start")) == week_start_iso:
                return step
        return None
    return None


def _pick(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Project a row onto the keys the page renders."""
    return {key: record.get(key) for key in keys}


def _group_by_date(
    records: list[dict[str, Any]], date_key: str, keys: tuple[str, ...]
) -> dict[str, list[dict[str, Any]]]:
    """Bucket rows by their (string) date, projected onto ``keys``."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        day = str(record.get(date_key))
        grouped.setdefault(day, []).append(_pick(record, keys))
    return grouped


def get_month_plan(
    conn: duckdb.DuckDBPyConnection,
    month: str,
    user_id: str = "default",
) -> dict[str, Any]:
    """Build the monthly plan grid: weeks x days, prescriptions vs actuals.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        month: Target month as ``YYYY-MM``.
        user_id: Profile owner identifier (defaults to ``"default"``).

    Returns:
        ``{"month", "week_start_day", "weeks", "blocks", "adherence"}`` where

        - ``weeks`` is one row per grid week (first week containing day 1
          through the last week containing the last day), each with
          ``week_start`` / ``week_end`` / ``in_month`` (the week lies entirely
          inside the month) / ``ladder_step`` / ``review_exists`` /
          ``adherence`` / ``days``;
        - each day carries ``date``, ``in_month``, its canonical
          ``prescriptions`` and the ``activities`` actually run;
        - ``blocks`` are the ledger blocks overlapping the grid range;
        - ``adherence`` totals only the days inside the month.

    Raises:
        ValueError: when ``month`` is not a ``YYYY-MM`` string.
    """
    first_day, last_day = _parse_month(month)
    start_day = get_week_start_day(conn, user_id)
    grid_start = week_start(first_day, start_day)
    grid_end = week_start(last_day, start_day) + _dt.timedelta(days=6)
    grid_start_iso, grid_end_iso = grid_start.isoformat(), grid_end.isoformat()

    prescriptions = _rows(
        conn,
        _SELECT_PRESCRIPTIONS,
        [user_id, user_id, grid_start_iso, grid_end_iso],
    )
    activities = _rows(conn, _SELECT_ACTIVITIES, [grid_start_iso, grid_end_iso])
    blocks = [
        _decode_block(record)
        for record in _rows(
            conn,
            _SELECT_BLOCKS_OVERLAPPING,
            [user_id, grid_end_iso, grid_start_iso],
        )
    ]
    review_weeks = {
        str(record["week_start_date"])
        for record in _rows(
            conn, _SELECT_REVIEW_WEEKS, [user_id, grid_start_iso, grid_end_iso]
        )
    }

    prescriptions_by_date = _group_by_date(prescriptions, "date", _PRESCRIPTION_KEYS)
    activities_by_date = _group_by_date(activities, "activity_date", _ACTIVITY_KEYS)

    weeks: list[dict[str, Any]] = []
    month_rows: list[dict[str, Any]] = []
    cursor = grid_start
    while cursor <= grid_end:
        days: list[dict[str, Any]] = []
        week_rows: list[dict[str, Any]] = []
        for offset in range(7):
            day = cursor + _dt.timedelta(days=offset)
            day_iso = day.isoformat()
            day_prescriptions = prescriptions_by_date.get(day_iso, [])
            in_month = first_day <= day <= last_day
            week_rows.extend(day_prescriptions)
            if in_month:
                month_rows.extend(day_prescriptions)
            days.append(
                {
                    "date": day_iso,
                    "in_month": in_month,
                    "prescriptions": day_prescriptions,
                    "activities": activities_by_date.get(day_iso, []),
                }
            )
        week_end = cursor + _dt.timedelta(days=6)
        weeks.append(
            {
                "week_start": cursor.isoformat(),
                "week_end": week_end.isoformat(),
                "in_month": first_day <= cursor and week_end <= last_day,
                "ladder_step": _ladder_step_for_week(blocks, cursor.isoformat()),
                "review_exists": cursor.isoformat() in review_weeks,
                "adherence": summarize_adherence(week_rows),
                "days": days,
            }
        )
        cursor += _dt.timedelta(days=7)

    return {
        "month": month,
        "week_start_day": start_day,
        "weeks": weeks,
        "blocks": [_pick(block, _BAND_KEYS) for block in blocks],
        "adherence": summarize_adherence(month_rows),
    }


def list_training_blocks(
    conn: duckdb.DuckDBPyConnection, user_id: str = "default"
) -> list[dict[str, Any]]:
    """List the whole mesocycle ledger in display order.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        user_id: Ledger owner identifier (defaults to ``"default"``).

    Returns:
        Blocks ordered by ``sequence`` with ``quality_types`` /
        ``long_run_ladder`` / ``cutback_rule`` JSON-decoded and dates as
        ``str``. Empty when no block is registered (or the table predates the
        ledger migration).
    """
    return [
        _decode_block(record) for record in _rows(conn, _SELECT_ALL_BLOCKS, [user_id])
    ]
