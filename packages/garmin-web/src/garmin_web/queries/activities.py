"""Read-only queries for the activities table."""

import json
import logging
from typing import Any

import duckdb

from garmin_web.queries.run_report import get_run_report

logger = logging.getLogger(__name__)

# How many of the newest activities get their run-report headline attached.
# The report is assembled on read over a 90-day window, so computing one per
# list row would turn a single request into hundreds of queries. Home shows the
# newest run and the list's first screen shows roughly this many, so older rows
# return ``None`` / ``[]`` instead (#1254).
RECENT_REPORT_ROWS = 10

# Each activity carries the opening sentence of its coach review, so the list
# can show what the run was without a second request. The LEFT JOINs keep
# activities that were never analysed; QUALIFY picks the newest run per
# activity the same way sections.py does (run_id, then analysis_id as a
# deterministic tiebreaker). The legacy ``summary`` section is still joined as
# the fallback for runs analysed before ``run_note`` existed (#1247).
_SELECT_ACTIVITIES = """
    SELECT
        activity_id,
        activity_date,
        activity_name,
        total_distance_km,
        total_time_seconds,
        avg_pace_seconds_per_km,
        avg_heart_rate,
        latest_summary.analysis_data AS summary_json,
        latest_run_note.analysis_data AS run_note_json
    FROM activities
    LEFT JOIN (
        SELECT activity_id, analysis_data
        FROM section_analyses
        WHERE section_type = 'summary'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY activity_id ORDER BY run_id DESC, analysis_id DESC
        ) = 1
    ) AS latest_summary USING (activity_id)
    LEFT JOIN (
        SELECT activity_id, analysis_data
        FROM section_analyses
        WHERE section_type = 'run_note'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY activity_id ORDER BY run_id DESC, analysis_id DESC
        ) = 1
    ) AS latest_run_note USING (activity_id)
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


def _section_payload(raw: str | None) -> dict[str, Any]:
    """Parse a section's stored JSON into a dict.

    Missing, malformed or unexpectedly shaped payloads degrade to ``{}``: a
    broken analysis must not take the activity list down.
    """
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _story_lead(run_note_raw: str | None, summary_raw: str | None) -> str | None:
    """The first sentence of the coach review, or of the legacy summary.

    ``run_note.story`` is the single review a run gets since #1251; runs
    analysed before it fall back to the old ``summary`` paragraph, and a run
    with neither returns ``None``.
    """
    story = _section_payload(run_note_raw).get("story")
    if isinstance(story, str):
        lead = lead_sentence(story)
        if lead is not None:
            return lead
    summary = _section_payload(summary_raw).get("summary")
    return lead_sentence(summary) if isinstance(summary, str) else None


def _headline_fields(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> tuple[str | None, list[str]]:
    """The run report's ``(plan_label, flag_labels)`` for one activity.

    Only the headline is read -- the plan verdict and the adverse signals are
    computed by the reader, so the list can never disagree with the single-run
    page about either. A database the report cannot be built from (an unknown
    activity, a fixture without the weather columns) degrades to
    ``(None, [])``.
    """
    try:
        report = get_run_report(conn, activity_id)
    except Exception as exc:  # pragma: no cover - degraded DB only
        logger.debug("no run report for activity %s: %s", activity_id, exc)
        return None, []
    headline = (report or {}).get("headline")
    if not isinstance(headline, dict):
        return None, []
    plan_label = headline.get("plan_label")
    flag_labels = headline.get("flag_labels")
    return (
        plan_label if isinstance(plan_label, str) else None,
        [label for label in flag_labels if isinstance(label, str)]
        if isinstance(flag_labels, list)
        else [],
    )


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
        avg_pace_seconds_per_km, avg_heart_rate, plan_label (str | None, e.g.
        "処方どおり"), flag_labels (list[str], the adverse signals) and
        story_lead (str | None, the first sentence of the coach review).
        ``plan_label`` / ``flag_labels`` are only filled in for the newest
        ``RECENT_REPORT_ROWS`` activities (#1254).
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
    for index, row in enumerate(rows):
        record = dict(zip(columns, row, strict=True))
        # DuckDB returns datetime.date; convert for JSON serialization
        record["activity_date"] = str(record["activity_date"])
        record["story_lead"] = _story_lead(
            record.pop("run_note_json"), record.pop("summary_json")
        )
        plan_label: str | None = None
        flag_labels: list[str] = []
        if index < RECENT_REPORT_ROWS:
            plan_label, flag_labels = _headline_fields(
                conn, int(record["activity_id"])
            )
        record["plan_label"] = plan_label
        record["flag_labels"] = flag_labels
        activities.append(record)
    return activities
