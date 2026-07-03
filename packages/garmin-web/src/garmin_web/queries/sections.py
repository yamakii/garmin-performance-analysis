"""Read-only queries for the section_analyses table with JSON parsing.

``section_analyses`` is append-only since #720: each analysis run appends a new
row per ``section_type`` instead of overwriting. Every row carries a ``run_id``
identifying the analysis run it belongs to (#776); one run = one version, shared
by all sections written in that run. The canonical result for a section is its
latest version (highest ``run_id``); a pinned ``run_id`` lets the detail page
view an older run as a snapshot (each section's latest version at or before that
run).
"""

import datetime as _dt
import json

import duckdb

# Latest version per section_type at or before an optional run_id pin. QUALIFY
# keeps the newest row per section_type by run_id (then analysis_id as a
# deterministic tiebreaker if a run wrote a section more than once).
_SELECT_LATEST = """
    SELECT section_type, analysis_data
    FROM section_analyses
    WHERE activity_id = ?
      AND (? IS NULL OR run_id <= ?)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY section_type ORDER BY run_id DESC, analysis_id DESC
    ) = 1
"""

# One row per analysis run (run_id), newest first. created_at is the run's
# newest timestamp (for display); section_types lists what that run wrote.
_SELECT_VERSIONS = """
    SELECT run_id,
           MAX(created_at) AS created_at,
           LIST(section_type ORDER BY section_type) AS section_types
    FROM section_analyses
    WHERE activity_id = ?
    GROUP BY run_id
    ORDER BY run_id DESC
"""


def get_sections(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    run_id: int | None = None,
) -> dict[str, dict]:
    """Fetch section analyses keyed by section_type.

    Returns the latest version of each section_type. When ``run_id`` is given,
    returns each section's latest version at or before that run (i.e. the state
    as of that analysis run). analysis_data is parsed as JSON; on parse failure
    the raw string is preserved for fallback rendering.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.
        run_id: Optional run_id pin. ``None`` returns the newest version of each
            section.

    Returns:
        {section_type: {"data": parsed_json | None,
                        "parse_error": bool,
                        "raw": str | None}}.
        raw is populated only when parsing failed.
    """
    rows = conn.execute(_SELECT_LATEST, [activity_id, run_id, run_id]).fetchall()

    sections: dict[str, dict] = {}
    for section_type, raw in rows:
        if raw is None:
            sections[section_type] = {"data": None, "parse_error": True, "raw": None}
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            sections[section_type] = {"data": None, "parse_error": True, "raw": raw}
        else:
            sections[section_type] = {"data": data, "parse_error": False, "raw": None}
    return sections


def list_section_versions(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> list[dict]:
    """List saved analysis runs for an activity, newest first.

    Each analysis run has a unique ``run_id`` shared by the sections written in
    that run (#776), so one run is exactly one version — a full-activity
    analysis of 5 sections is a single version, not five.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        A list of ``{"run_id": int, "created_at": iso8601 str,
        "section_types": list[str]}`` ordered by ``run_id`` descending (newest
        first). Empty when the activity has no section analyses.
    """
    rows = conn.execute(_SELECT_VERSIONS, [activity_id]).fetchall()
    versions: list[dict] = []
    for run_id, created_at, section_types in rows:
        stamp = (
            str(created_at)
            if isinstance(created_at, _dt.date | _dt.datetime)
            else created_at
        )
        versions.append(
            {
                "run_id": run_id,
                "created_at": stamp,
                "section_types": list(section_types),
            }
        )
    return versions
