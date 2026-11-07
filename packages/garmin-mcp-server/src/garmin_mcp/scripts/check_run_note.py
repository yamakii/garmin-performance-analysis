"""Check a run_note against a run report without touching DuckDB.

The coach-review eval (``.claude/hillclimb/coach-review/``) grades the
``run_note.json`` a headless run-note-analyst wrote. It must apply the same two
gates ``merge_section_analyses`` applies -- the section schema and the grounding
check -- but never insert anything, so this CLI takes the report and the note
as files and prints the verdict.

Usage:
    uv run python -m garmin_mcp.scripts.check_run_note \\
        --report /tmp/report.json --note /tmp/run_note.json

``--note`` accepts either the full section payload (with ``analysis_data``) or
the bare ``analysis_data`` mapping. The exit status is always 0; the verdict is
the printed JSON ``{"schema_ok", "grounding_ok", "errors"}``.
"""

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from garmin_mcp.validation.section_schemas import validate_section_data
from garmin_mcp.validation.validators import check_run_note_grounding


def _analysis_data(note: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the ``analysis_data`` of a section payload, or the note itself."""
    inner = note.get("analysis_data")
    return inner if isinstance(inner, Mapping) else note


def check(report: dict, note: dict) -> dict:
    """Run the schema and grounding gates on one run_note.

    Args:
        report: The deterministic run report the note was written against.
        note: The run_note section payload or its bare ``analysis_data``.

    Returns:
        ``{"schema_ok": bool, "grounding_ok": bool, "errors": list[str]}``.
    """
    data = _analysis_data(note)
    errors: list[str] = []
    schema_ok, schema_errors = validate_section_data("run_note", dict(data))
    errors.extend(f"schema: {e}" for e in schema_errors)
    try:
        grounding_ok, reason = check_run_note_grounding(data, report)
    except Exception as e:  # a malformed note must not crash the grader
        grounding_ok, reason = False, f"grounding check raised: {e}"
    if not grounding_ok:
        errors.append(f"grounding: {reason}")
    return {"schema_ok": schema_ok, "grounding_ok": grounding_ok, "errors": errors}


def _load(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Always returns 0; the verdict is printed as JSON."""
    parser = argparse.ArgumentParser(
        description="Check a run_note.json against a run report (read-only)"
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--note", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report = _load(args.report)
        note = _load(args.note)
    except (OSError, ValueError) as e:
        result = {"schema_ok": False, "grounding_ok": False, "errors": [str(e)]}
    else:
        if not isinstance(report, dict) or not isinstance(note, dict):
            result = {
                "schema_ok": False,
                "grounding_ok": False,
                "errors": ["report and note must both be JSON objects"],
            }
        else:
            result = check(report, note)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
