"""Read-only queries for the section_analyses table with JSON parsing."""

import json

import duckdb


def get_sections(conn: duckdb.DuckDBPyConnection, activity_id: int) -> dict[str, dict]:
    """Fetch section analyses keyed by section_type.

    When multiple rows exist for the same section_type, the most recently
    created row wins. analysis_data is parsed as JSON; on parse failure
    the raw string is preserved for fallback rendering.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        {section_type: {"data": parsed_json | None,
                        "parse_error": bool,
                        "raw": str | None}}.
        raw is populated only when parsing failed.
    """
    rows = conn.execute(
        "SELECT section_type, analysis_data FROM section_analyses"
        " WHERE activity_id = ? ORDER BY created_at",
        [activity_id],
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
