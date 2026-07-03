"""Save a trend-narration ``trend.json`` into the ``trend_analyses`` table.

The ``trend-narration`` workflow (issue #792, parent #701) writes a single
``trend.json`` into a temp dir during its Analyze phase. This script is the
Finalize/merge step: it reads that file, validates the required structure, and
appends a new version via :func:`insert_trend_analysis` (append-only, one row per
run — see #789). Mirrors ``merge_section_analyses`` for the per-activity pipeline.

Usage::

    uv run --directory packages/garmin-mcp-server \
      python -m garmin_mcp.scripts.save_trend_narration /tmp/trend_week_2026-06-22_123
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis

_REQUIRED_KEYS = ("granularity", "period_start", "period_end", "analysis_data")

AGENT_NAME = "trend-narration"


def save_trend_narration(temp_dir: str, db_path: str | None = None) -> dict[str, Any]:
    """Read ``<temp_dir>/trend.json`` and append it to ``trend_analyses``.

    Args:
        temp_dir: Directory holding the workflow's ``trend.json`` output.
        db_path: Optional DuckDB path (defaults to the configured database).

    Returns:
        ``{"saved": bool, "granularity": str, "period_start": str}``.

    Raises:
        FileNotFoundError: When ``trend.json`` is absent.
        ValueError: When a required key is missing or ``analysis_data`` is not a
            dict (fail-closed — never persist a malformed narration row).
    """
    path = os.path.join(temp_dir, "trend.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"trend.json not found in {temp_dir}")

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"trend.json missing required keys: {missing}")
    if not isinstance(data["analysis_data"], dict):
        raise ValueError("trend.json 'analysis_data' must be an object")
    if data["granularity"] not in ("week", "month"):
        raise ValueError(f"invalid granularity: {data['granularity']!r}")

    trend = {
        "granularity": data["granularity"],
        "period_start": data["period_start"],
        "period_end": data["period_end"],
        "analysis_data": data["analysis_data"],
        "user_id": data.get("user_id") or "default",
        "agent_name": AGENT_NAME,
    }
    saved = insert_trend_analysis(trend, db_path=db_path)
    return {
        "saved": saved,
        "granularity": data["granularity"],
        "period_start": data["period_start"],
    }


def main() -> int:
    """CLI entrypoint. Prints one-line JSON; returns 0 on save, 1 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("temp_dir", help="Directory containing trend.json")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Explicit DuckDB path (default: configured database).",
    )
    args = parser.parse_args()

    result = save_trend_narration(args.temp_dir, db_path=args.db_path)
    print(json.dumps(result, default=str))
    return 0 if result["saved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
