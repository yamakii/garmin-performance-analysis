"""Read-only queries for the activities table."""

import json

import duckdb

# Each activity carries the star rating and the opening sentence of its latest
# summary section, so the list can show a verdict without a second request
# (#1131). The LEFT JOIN keeps activities that were never analysed; QUALIFY
# picks the newest run per activity the same way sections.py does (run_id, then
# analysis_id as a deterministic tiebreaker).
_SELECT_ACTIVITIES = """
    SELECT
        activity_id,
        activity_date,
        activity_name,
        total_distance_km,
        total_time_seconds,
        avg_pace_seconds_per_km,
        avg_heart_rate,
        latest_summary.analysis_data AS summary_json
    FROM activities
    LEFT JOIN (
        SELECT activity_id, analysis_data
        FROM section_analyses
        WHERE section_type = 'summary'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY activity_id ORDER BY run_id DESC, analysis_id DESC
        ) = 1
    ) AS latest_summary USING (activity_id)
"""


def lead_sentence(text: str | None) -> str | None:
    """Return the first sentence of ``text`` (up to and including 「。」).

    Falls back to the whole (stripped) text when there is no 「。」. ``None`` and
    blank text return ``None``.
    """
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    end = stripped.find("。")
    if end == -1:
        return stripped
    return stripped[: end + 1]


def _summary_fields(raw: str | None) -> tuple[str | None, str | None]:
    """Parse (star_rating, summary_lead) out of a summary section's JSON.

    Missing, malformed or unexpectedly shaped payloads degrade to (None, None):
    a broken analysis must not take the activity list down.
    """
    if not raw:
        return None, None
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    star_rating = payload.get("star_rating")
    if not isinstance(star_rating, str):
        star_rating = None
    summary = payload.get("summary")
    summary_lead = lead_sentence(summary) if isinstance(summary, str) else None
    return star_rating, summary_lead


def list_activities(
    conn: duckdb.DuckDBPyConnection,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """List activities sorted by activity_date descending.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        from_date: Inclusive lower bound (YYYY-MM-DD), or None.
        to_date: Inclusive upper bound (YYYY-MM-DD), or None.

    Returns:
        List of dicts with keys: activity_id, activity_date (str),
        activity_name, total_distance_km, total_time_seconds,
        avg_pace_seconds_per_km, avg_heart_rate, star_rating (str | None,
        e.g. "★★★★☆ 4.2/5.0") and summary_lead (str | None) from the latest
        summary section analysis.
    """
    sql = _SELECT_ACTIVITIES
    conditions: list[str] = []
    params: list[str] = []
    if from_date is not None:
        conditions.append("activity_date >= ?")
        params.append(from_date)
    if to_date is not None:
        conditions.append("activity_date <= ?")
        params.append(to_date)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY activity_date DESC"

    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    rows = result.fetchall()

    activities = []
    for row in rows:
        record = dict(zip(columns, row, strict=True))
        # DuckDB returns datetime.date; convert for JSON serialization
        record["activity_date"] = str(record["activity_date"])
        star_rating, summary_lead = _summary_fields(record.pop("summary_json"))
        record["star_rating"] = star_rating
        record["summary_lead"] = summary_lead
        activities.append(record)
    return activities
