"""Trend analyses DB inserter.

Persists weekly / monthly longitudinal trend narratives (issue #789, parent
#701) into the ``trend_analyses`` table.

Write semantics:
- Append-only: every save inserts a fresh row. Re-saving the same
  ``(user_id, granularity, period_start)`` appends a new version rather than
  overwriting the prior one, preserving the full narration history. The reader
  returns the latest version (highest ``created_at``) per period as canonical.
- The free-form ``analysis_data`` payload is serialized to JSON and stored as a
  VARCHAR column.
- Surrogate keys are drawn from ``seq_trend_analyses_id`` via ``nextval`` and
  ``created_at`` is left to the table DEFAULT (``CURRENT_TIMESTAMP``), mirroring
  the ``insert_weekly_review`` pattern.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def insert_trend_analysis(trend: dict[str, Any], db_path: str | None = None) -> bool:
    """Insert a trend analysis record, appending a new version (no overwrite).

    Args:
        trend: Trend dict with keys ``granularity`` (``'week'`` | ``'month'``),
            ``period_start``, ``period_end``, ``analysis_data`` (dict, serialized
            to JSON), ``user_id`` (defaults to ``"default"``), ``agent_name``,
            and ``agent_version`` (defaults to ``"1.0"``).
        db_path: Path to DuckDB database. If None, uses default.

    Returns:
        ``True`` on success.
    """
    if db_path is None:
        from garmin_mcp.utils.paths import get_database_dir

        db_path = str(get_database_dir() / "garmin_performance.duckdb")

    from garmin_mcp.database.connection import get_write_connection

    user_id = trend.get("user_id") or "default"
    agent_version = trend.get("agent_version") or "1.0"
    analysis_data_json = json.dumps(trend.get("analysis_data"), ensure_ascii=False)

    with get_write_connection(db_path) as conn:
        # Always INSERT a new version; same-period re-saves append rather than
        # overwrite. created_at is left to the table DEFAULT (CURRENT_TIMESTAMP).
        conn.execute(
            """
            INSERT INTO trend_analyses (
                analysis_id, user_id, granularity, period_start, period_end,
                analysis_data, agent_name, agent_version
            ) VALUES (
                nextval('seq_trend_analyses_id'), ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                user_id,
                trend.get("granularity"),
                trend.get("period_start"),
                trend.get("period_end"),
                analysis_data_json,
                trend.get("agent_name"),
                agent_version,
            ],
        )

        logger.info(
            "Saved trend analysis user_id=%s granularity=%s period_start=%s",
            user_id,
            trend.get("granularity"),
            trend.get("period_start"),
        )

    return True
