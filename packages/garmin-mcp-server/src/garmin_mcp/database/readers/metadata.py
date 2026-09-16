"""
Metadata reader for activity queries.

Handles activity date and ID lookups.
"""

import logging
from typing import Any

from garmin_mcp.analysis.derivations import format_gear_label, is_new_gear
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
        first_use_date, runs_on_gear, km_on_gear and is_new_gear -- or None
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
            )
            SELECT
                t.gear_type,
                t.gear_model,
                t.gear_nickname,
                MIN(a.activity_date) AS first_use_date,
                COUNT(*) AS runs_on_gear,
                COALESCE(SUM(a.total_distance_km), 0) AS km_on_gear
            FROM target t
            JOIN activities a
              ON {_GEAR_KEY.format(alias="a")} = t.gear_key
             AND (a.activity_date, a.activity_id) <= (t.activity_date, t.activity_id)
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
    return {
        "gear_type": row[0],
        "gear_model": row[1],
        "gear_nickname": row[2],
        "gear_label": format_gear_label(row[1], row[2]),
        "first_use_date": str(row[3]) if row[3] is not None else None,
        "runs_on_gear": runs_on_gear,
        "km_on_gear": round(float(row[5]), 1),
        "is_new_gear": is_new_gear(runs_on_gear),
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
                    COUNT(*) AS runs_total
                FROM activities
                WHERE gear_model IS NOT NULL
                  AND activity_date <= ?
                GROUP BY gear_key
            )
            SELECT
                ANY_VALUE(w.gear_model) AS gear_model,
                ANY_VALUE(w.gear_nickname) AS gear_nickname,
                ANY_VALUE(w.gear_type) AS gear_type,
                COUNT(*) AS runs,
                COALESCE(SUM(w.total_distance_km), 0) AS km,
                ANY_VALUE(h.first_use_date) AS first_use_date,
                ANY_VALUE(h.runs_total) AS runs_on_gear_total
            FROM activities w
            JOIN history h ON h.gear_key = {_GEAR_KEY.format(alias="w")}
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
            "is_new_gear": is_new_gear(int(row[6])),
        }
        for row in rows
    ]
