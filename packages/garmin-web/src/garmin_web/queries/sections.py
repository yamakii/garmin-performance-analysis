"""Read-only queries for the section_analyses table with JSON parsing.

``section_analyses`` is append-only since #720: each analysis run appends a new
row per ``section_type`` instead of overwriting. The canonical result for a
section is its latest version (highest ``created_at``); a pinned ``created_at``
lets the detail page view an older run. Versions are grouped into batches (one
analysis run = rows sharing a ``created_at``) for the version selector.
"""

import datetime as _dt
import json

import duckdb

# Latest version per section_type at or before an optional created_at pin.
# QUALIFY keeps the newest row per section_type (created_at, then analysis_id as
# a deterministic tiebreaker when a run writes rows in the same timestamp).
_SELECT_LATEST = """
    SELECT section_type, analysis_data
    FROM section_analyses
    WHERE activity_id = ?
      AND (? IS NULL OR created_at <= ?)
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY section_type ORDER BY created_at DESC, analysis_id DESC
    ) = 1
"""

# Distinct analysis batches (one run = rows sharing created_at), newest first.
_SELECT_VERSIONS = """
    SELECT created_at, LIST(section_type ORDER BY section_type) AS section_types
    FROM section_analyses
    WHERE activity_id = ?
    GROUP BY created_at
    ORDER BY created_at DESC
"""


def get_sections(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    created_at: str | None = None,
) -> dict[str, dict]:
    """Fetch section analyses keyed by section_type.

    Returns the latest version of each section_type. When ``created_at`` is
    given, returns each section's latest version at or before that timestamp
    (i.e. the state as of that analysis run). analysis_data is parsed as JSON;
    on parse failure the raw string is preserved for fallback rendering.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.
        created_at: Optional ISO 8601 timestamp pin. ``None`` returns the
            newest version of each section.

    Returns:
        {section_type: {"data": parsed_json | None,
                        "parse_error": bool,
                        "raw": str | None}}.
        raw is populated only when parsing failed.
    """
    rows = conn.execute(
        _SELECT_LATEST, [activity_id, created_at, created_at]
    ).fetchall()

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
    """List saved analysis batches for an activity, newest first.

    Each analysis run appends rows sharing a ``created_at``; this groups those
    rows into one version entry so the detail page can switch between past runs.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        A list of ``{"created_at": iso8601 str, "section_types": list[str]}``
        ordered by ``created_at`` descending (newest first). Empty when the
        activity has no section analyses.
    """
    rows = conn.execute(_SELECT_VERSIONS, [activity_id]).fetchall()
    versions: list[dict] = []
    for created_at, section_types in rows:
        stamp = (
            str(created_at)
            if isinstance(created_at, _dt.date | _dt.datetime)
            else created_at
        )
        versions.append(
            {"created_at": stamp, "section_types": list(section_types)}
        )
    return versions
