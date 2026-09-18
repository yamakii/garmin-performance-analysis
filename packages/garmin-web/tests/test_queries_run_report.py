"""Tests for garmin_web.queries.run_report.get_run_report (#1250).

The query layer is a delegator, so what is worth pinning is that the request's
connection reaches the reader and that an unknown activity comes back as
``None`` (which the route turns into a 404) rather than as an empty dict.
"""

from pathlib import Path

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.run_report import get_run_report

# Mirrors conftest.FULL_ACTIVITY_ID (fully-populated detail fixture row).
FULL_ACTIVITY_ID = 9000000101


@pytest.mark.integration
def test_run_report_query_returns_report(detail_db_path: Path) -> None:
    """The fixture activity's report is assembled through the reader."""
    with get_connection(detail_db_path) as conn:
        report = get_run_report(conn, FULL_ACTIVITY_ID)

    assert report is not None
    assert report["activity_id"] == FULL_ACTIVITY_ID
    assert report["activity_date"] == "2025-10-09"
    assert set(report) >= {
        "headline",
        "plan",
        "signals",
        "moments",
        "zones",
        "conditions",
    }


@pytest.mark.integration
def test_run_report_query_unknown_activity_is_none(detail_db_path: Path) -> None:
    """An unknown activity yields ``None`` so the route can answer 404."""
    with get_connection(detail_db_path) as conn:
        assert get_run_report(conn, 999999) is None
