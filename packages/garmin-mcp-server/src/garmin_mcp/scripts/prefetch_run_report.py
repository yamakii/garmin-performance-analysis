"""Print the deterministic run report for one activity (Epic #1247).

A thin stdout wrapper around ``GarminDBReader.get_run_report`` so the
``analyze-activity`` fetch stage can hand the report to the run-note agent the
same way it hands over the prefetch bundle: one shell call, one line of JSON,
no reader import inside an agent.

Nothing is computed here -- ``database.readers.run_report`` decides every value
(see its module docstring for who owns what).

Usage:
    uv run python -m garmin_mcp.scripts.prefetch_run_report 24407019887

Output (JSON to stdout): the report dict itself, or
``{"error": ..., "activity_id": ...}`` with exit code 1 when the activity is
not in DuckDB, so the caller fails loudly instead of analysing an empty run.
"""

import argparse
import json
import sys
from typing import Any

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_reader import GarminDBReader


def prefetch_run_report(activity_id: int) -> dict[str, Any]:
    """Return the run report for ``activity_id``, or an ``error`` dict.

    Args:
        activity_id: Garmin activity ID.

    Returns:
        The deterministic run report, or ``{"error", "activity_id"}`` when the
        activity does not exist (or the read failed).
    """
    try:
        report = GarminDBReader(str(get_db_path())).get_run_report(activity_id)
    except Exception as e:  # pragma: no cover - defensive, surfaced as JSON
        return {"error": f"run report failed: {e}", "activity_id": activity_id}

    if report is None:
        return {
            "error": f"activity {activity_id} not found in DuckDB",
            "activity_id": activity_id,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the deterministic run report for one activity"
    )
    parser.add_argument("activity_id", type=int, help="Garmin activity ID")
    args = parser.parse_args()

    result = prefetch_run_report(args.activity_id)
    print(json.dumps(result, ensure_ascii=False))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
