"""
Metadata reader for activity queries.

Handles activity date and ID lookups.
"""

import logging
from typing import Any

from garmin_mcp.analysis.derivations import (
    classify_gear_age,
    classify_gear_wear,
    format_gear_label,
    gear_age_months,
    gear_wear_pct,
    is_new_gear,
    replace_recommended,
)
from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class MetadataReader(BaseDBReader):
    """Reader for activity metadata queries."""

    # Columns on the ``activities`` table that may be bulk-fetched via
    # ``get_bulk_activity_fields``. Used as an allowlist to prevent SQL
    # injection through dynamically interpolated column names.
    ACTIVITY_FIELD_ALLOWLIST: frozenset[str] = frozenset(
        {
            "activity_date",
            "activity_name",
            "total_distance_km",
            "total_time_seconds",
            "avg_speed_ms",
            "avg_pace_seconds_per_km",
            "avg_heart_rate",
            "max_heart_rate",
            "temp_celsius",
            "relative_humidity_percent",
            "wind_speed_kmh",
        }
    )

    def get_activity_date(self, activity_id: int) -> str | None:
        """
        Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date in YYYY-MM-DD format, or None if not found
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT activity_date FROM activities WHERE activity_id = ?",
                    [activity_id],
                ).fetchone()

            if result:
                return str(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity date: {e}")
            return None

    def query_activity_by_date(self, date: str) -> int | None:
        """
        Query activity ID by date from DuckDB.

        Args:
            date: Activity date in YYYY-MM-DD format

        Returns:
            Activity ID if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    "SELECT activity_id FROM activities WHERE activity_date = ?",
                    [date],
                ).fetchone()

            if result:
                return int(result[0])
            return None
        except Exception as e:
            logger.error(f"Error querying activity by date: {e}")
            return None

    def get_activity_dates(self, activity_ids: list[int]) -> dict[int, str]:
        """Bulk-fetch activity dates for multiple activities in one query.

        Args:
            activity_ids: List of activity IDs

        Returns:
            Dict mapping activity_id -> activity_date (YYYY-MM-DD str).
            Activities without a stored date are omitted.
        """
        if not activity_ids:
            return {}

        placeholders = ",".join(["?"] * len(activity_ids))
        sql = (
            "SELECT activity_id, activity_date "
            f"FROM activities WHERE activity_id IN ({placeholders})"
        )
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, activity_ids).fetchall()
            return {int(row[0]): str(row[1]) for row in rows if row[1] is not None}
        except Exception as e:
            logger.error(f"Error bulk-querying activity dates: {e}")
            return {}

    def get_bulk_activity_fields(
        self, activity_ids: list[int], fields: list[str]
    ) -> dict[int, dict[str, Any]]:
        """Bulk-fetch arbitrary ``activities`` columns in a single query.

        Args:
            activity_ids: List of activity IDs
            fields: Column names to fetch. Each must be in
                ``ACTIVITY_FIELD_ALLOWLIST`` (validated to prevent SQL
                injection via dynamic column interpolation).

        Returns:
            Dict mapping activity_id -> {field: value}. Activities not found
            in the table are omitted.

        Raises:
            ValueError: If any requested field is not in the allowlist.
        """
        if not fields:
            return {}

        invalid = [f for f in fields if f not in self.ACTIVITY_FIELD_ALLOWLIST]
        if invalid:
            raise ValueError(f"Invalid activity field(s): {invalid}")

        if not activity_ids:
            return {}

        # Deduplicate fields while preserving order for stable column mapping.
        ordered_fields = list(dict.fromkeys(fields))
        columns_sql = ", ".join(ordered_fields)
        placeholders = ",".join(["?"] * len(activity_ids))
        sql = (
            f"SELECT activity_id, {columns_sql} "
            f"FROM activities WHERE activity_id IN ({placeholders})"
        )
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, activity_ids).fetchall()
            result: dict[int, dict[str, Any]] = {}
            for row in rows:
                activity_id = int(row[0])
                result[activity_id] = {
                    field: row[idx + 1] for idx, field in enumerate(ordered_fields)
                }
            return result
        except Exception as e:
            logger.error(f"Error bulk-querying activity fields: {e}")
            return {}


# ---------------------------------------------------------------------------
# Gear usage (Issue #1207). Gear has always been ingested into the activities
# table but nothing read it back out, so a single-activity workflow had no way
# to see which shoe was worn. These take an already-open connection because
# both prefetch scripts hold one -- going through MetadataReader would open a
# second connection inside their read transaction.
#
# Shoes are identified by ``gear_uuid``, not by name. Garmin's newer gear form
# leaves ``gear_model`` as the base model, so a replacement pair of the same
# shoe reuses the string and would otherwise inherit its predecessor's mileage.
# ``gear_model`` is the fallback for rows ingested before gear_uuid existed.
# ---------------------------------------------------------------------------

# Shoe identity for grouping. Written as a SQL fragment so the per-activity and
# per-week queries below cannot drift apart on how a shoe is identified.
_GEAR_KEY = "COALESCE({alias}.gear_uuid, {alias}.gear_model)"

# Latest known lifecycle values per shoe (Issue #1209). The replacement limit,
# status and dates are snapshots written at each activity's ingest and they do
# change for the same pair -- one shoe is observed going active -> retired --
# so the newest row wins. Shared by both queries for the same reason as
# _GEAR_KEY: one definition of "current" per shoe.
_GEAR_LATEST_CTE = f"""
    gear_latest AS (
        SELECT
            gear_key, gear_max_km, gear_status, gear_since_date, gear_retired_date
        FROM (
            SELECT
                {_GEAR_KEY.format(alias="activities")} AS gear_key,
                gear_max_km,
                gear_status,
                gear_since_date,
                gear_retired_date,
                ROW_NUMBER() OVER (
                    PARTITION BY {_GEAR_KEY.format(alias="activities")}
                    ORDER BY activity_date DESC, activity_id DESC
                ) AS rn
            FROM activities
            WHERE {_GEAR_KEY.format(alias="activities")} IS NOT NULL
        )
        WHERE rn = 1
    )
"""


def _gear_lifecycle_block(
    km_on_gear: float,
    max_km: float | None,
    since_date: Any,
    retired_date: Any,
    status: str | None,
    as_of: str | None,
) -> dict[str, Any]:
    """Derive the wear / age / replacement fields shared by both collectors.

    ``as_of`` anchors the age so a re-analyzed old run reports the age that
    applied then, matching how mileage is counted as of that run.

    A shoe counts as retired when Garmin says so or a retirement date exists.
    A NULL status means "not recorded yet" (rows ingested before #1209) and is
    deliberately NOT read as retired -- a stale listing beats a missed alert.
    """
    wear_pct = gear_wear_pct(km_on_gear, max_km)
    wear_status = classify_gear_wear(wear_pct)
    since = str(since_date) if since_date is not None else None
    age_months = gear_age_months(since, as_of)
    age_status = classify_gear_age(age_months)
    return {
        "max_km": max_km,
        "wear_pct": wear_pct,
        "wear_status": wear_status,
        "since_date": since,
        "age_months": age_months,
        "age_status": age_status,
        "is_retired": status == "retired" or retired_date is not None,
        "replace_recommended": replace_recommended(wear_status, age_status),
    }


def collect_activity_gear(conn: Any, activity_id: int) -> dict[str, Any] | None:
    """Return the gear block for one activity, or None when no gear is recorded.

    ``runs_on_gear`` / ``km_on_gear`` are cumulative up to and including this
    activity (ordered by activity_date, then activity_id), so re-analyzing an
    old run reports the mileage as of that run rather than today's.

    Args:
        conn: Open DuckDB connection.
        activity_id: Activity to describe.

    Returns:
        Dict with gear_type, gear_model, gear_nickname, gear_label,
        first_use_date, runs_on_gear, km_on_gear, is_new_gear plus the
        lifecycle block (max_km, wear_pct, wear_status, since_date,
        age_months, age_status, is_retired, replace_recommended) -- or None
        when the activity is unknown or has no gear recorded.
    """
    try:
        row = conn.execute(
            f"""
            WITH target AS (
                SELECT
                    activity_id,
                    activity_date,
                    gear_type,
                    gear_model,
                    gear_nickname,
                    {_GEAR_KEY.format(alias="activities")} AS gear_key
                FROM activities
                WHERE activity_id = ?
            ),
            {_GEAR_LATEST_CTE}
            SELECT
                t.gear_type,
                t.gear_model,
                t.gear_nickname,
                MIN(a.activity_date) AS first_use_date,
                COUNT(*) AS runs_on_gear,
                COALESCE(SUM(a.total_distance_km), 0) AS km_on_gear,
                ANY_VALUE(t.activity_date) AS as_of,
                ANY_VALUE(g.gear_max_km) AS gear_max_km,
                ANY_VALUE(g.gear_status) AS gear_status,
                ANY_VALUE(g.gear_since_date) AS gear_since_date,
                ANY_VALUE(g.gear_retired_date) AS gear_retired_date
            FROM target t
            JOIN activities a
              ON {_GEAR_KEY.format(alias="a")} = t.gear_key
             AND (a.activity_date, a.activity_id) <= (t.activity_date, t.activity_id)
            LEFT JOIN gear_latest g ON g.gear_key = t.gear_key
            GROUP BY t.gear_type, t.gear_model, t.gear_nickname
            """,
            [activity_id],
        ).fetchone()
    except Exception as e:
        logger.error(f"Error querying activity gear for {activity_id}: {e}")
        return None

    # No gear recorded: the join finds nothing, so there is no row at all. The
    # null-count guard covers a grouped row that somehow carries no count.
    if not row or row[4] is None:
        return None

    runs_on_gear = int(row[4])
    km_on_gear = round(float(row[5]), 1)
    return {
        "gear_type": row[0],
        "gear_model": row[1],
        "gear_nickname": row[2],
        "gear_label": format_gear_label(row[1], row[2]),
        "first_use_date": str(row[3]) if row[3] is not None else None,
        "runs_on_gear": runs_on_gear,
        "km_on_gear": km_on_gear,
        "is_new_gear": is_new_gear(runs_on_gear),
        # Wear / age are anchored on this run's date, like the mileage above.
        **_gear_lifecycle_block(
            km_on_gear,
            row[7],
            row[9],
            row[10],
            row[8],
            str(row[6]) if row[6] is not None else None,
        ),
    }


def collect_week_gear_usage(conn: Any, start: str, end: str) -> list[dict[str, Any]]:
    """Per-shoe usage inside ``[start, end]``, ordered by km desc.

    ``runs`` / ``km`` cover the window only; ``runs_on_gear_total`` is the
    cumulative run count through ``end``, which is what ``is_new_gear`` keys on
    so a shoe bought mid-window is still flagged as new.

    Args:
        conn: Open DuckDB connection.
        start: Window start date (YYYY-MM-DD), inclusive.
        end: Window end date (YYYY-MM-DD), inclusive.

    Returns:
        One dict per shoe used in the window; empty list when none.
    """
    try:
        rows = conn.execute(
            f"""
            WITH history AS (
                SELECT
                    {_GEAR_KEY.format(alias="activities")} AS gear_key,
                    MIN(activity_date) AS first_use_date,
                    COUNT(*) AS runs_total,
                    COALESCE(SUM(total_distance_km), 0) AS km_total
                FROM activities
                WHERE gear_model IS NOT NULL
                  AND activity_date <= ?
                GROUP BY gear_key
            ),
            {_GEAR_LATEST_CTE}
            SELECT
                ANY_VALUE(w.gear_model) AS gear_model,
                ANY_VALUE(w.gear_nickname) AS gear_nickname,
                ANY_VALUE(w.gear_type) AS gear_type,
                COUNT(*) AS runs,
                COALESCE(SUM(w.total_distance_km), 0) AS km,
                ANY_VALUE(h.first_use_date) AS first_use_date,
                ANY_VALUE(h.runs_total) AS runs_on_gear_total,
                ANY_VALUE(h.km_total) AS km_on_gear_total,
                ANY_VALUE(g.gear_max_km) AS gear_max_km,
                ANY_VALUE(g.gear_status) AS gear_status,
                ANY_VALUE(g.gear_since_date) AS gear_since_date,
                ANY_VALUE(g.gear_retired_date) AS gear_retired_date
            FROM activities w
            JOIN history h ON h.gear_key = {_GEAR_KEY.format(alias="w")}
            LEFT JOIN gear_latest g ON g.gear_key = {_GEAR_KEY.format(alias="w")}
            WHERE w.gear_model IS NOT NULL
              AND w.activity_date BETWEEN ? AND ?
            GROUP BY {_GEAR_KEY.format(alias="w")}
            ORDER BY km DESC, gear_model ASC
            """,
            [end, start, end],
        ).fetchall()
    except Exception as e:
        logger.error(f"Error querying week gear usage for {start}..{end}: {e}")
        return []

    return [
        {
            "gear_model": row[0],
            "gear_nickname": row[1],
            "gear_label": format_gear_label(row[0], row[1]),
            "gear_type": row[2],
            "runs": int(row[3]),
            "km": round(float(row[4]), 1),
            "first_use_date": str(row[5]) if row[5] is not None else None,
            "runs_on_gear_total": int(row[6]),
            "km_on_gear_total": round(float(row[7]), 1),
            "is_new_gear": is_new_gear(int(row[6])),
            # Wear is the shoe's whole life through the window end, not the
            # window's own mileage -- a pair does not reset each week.
            **_gear_lifecycle_block(
                round(float(row[7]), 1), row[8], row[10], row[11], row[9], end
            ),
        }
        for row in rows
    ]


def collect_gear_roster(
    conn: Any, include_retired: bool = False, as_of: str | None = None
) -> list[dict[str, Any]]:
    """Every shoe with its lifetime mileage and replacement verdict.

    This is the alert surface: one row per shoe, most-worn first, so a pair
    approaching its limit is visible without asking about a specific run.

    Args:
        conn: Open DuckDB connection.
        include_retired: Include shoes Garmin marks retired (or with a
            retirement date). Default False -- a retired pair needs no alert.
        as_of: Reference date for the age axis, YYYY-MM-DD. Defaults to today.

    Returns:
        One dict per shoe, ordered by wear_pct desc (unknown wear last).
    """
    try:
        rows = conn.execute(f"""
            WITH {_GEAR_LATEST_CTE}
            SELECT
                ANY_VALUE(a.gear_model) AS gear_model,
                ANY_VALUE(a.gear_nickname) AS gear_nickname,
                ANY_VALUE(a.gear_type) AS gear_type,
                ANY_VALUE(a.gear_uuid) AS gear_uuid,
                COUNT(*) AS runs,
                COALESCE(SUM(a.total_distance_km), 0) AS km,
                MIN(a.activity_date) AS first_use_date,
                MAX(a.activity_date) AS last_used,
                ANY_VALUE(g.gear_max_km) AS gear_max_km,
                ANY_VALUE(g.gear_status) AS gear_status,
                ANY_VALUE(g.gear_since_date) AS gear_since_date,
                ANY_VALUE(g.gear_retired_date) AS gear_retired_date
            FROM activities a
            LEFT JOIN gear_latest g ON g.gear_key = {_GEAR_KEY.format(alias="a")}
            WHERE {_GEAR_KEY.format(alias="a")} IS NOT NULL
            GROUP BY {_GEAR_KEY.format(alias="a")}
            """).fetchall()
    except Exception as e:
        logger.error(f"Error querying gear roster: {e}")
        return []

    roster: list[dict[str, Any]] = []
    for row in rows:
        km = round(float(row[5]), 1)
        lifecycle = _gear_lifecycle_block(km, row[8], row[10], row[11], row[9], as_of)
        if lifecycle["is_retired"] and not include_retired:
            continue
        roster.append(
            {
                "gear_label": format_gear_label(row[0], row[1]),
                "gear_model": row[0],
                "gear_nickname": row[1],
                "gear_type": row[2],
                "gear_uuid": row[3],
                "runs": int(row[4]),
                "km": km,
                "first_use_date": str(row[6]) if row[6] is not None else None,
                "last_used": str(row[7]) if row[7] is not None else None,
                **lifecycle,
            }
        )

    # Most worn first; shoes with no recorded limit sort last (they cannot be
    # ranked, and pretending they are unworn would bury a real alert).
    roster.sort(
        key=lambda r: (
            r["wear_pct"] is None,
            -(r["wear_pct"] or 0.0),
            r["gear_label"] or "",
        )
    )
    return roster
