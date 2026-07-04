"""Tests for trend_pending detection inside catch_up_ingest (issue #810).

Detection was moved from ``scripts/scheduled_sync`` into ``catch_up_ingest`` so
that any caller (the scheduled-sync cron and the weekly-review skill, both of
which go through the ``catch_up_ingest`` MCP tool) receives ``trend_pending``
for the last completed week still lacking a narration. The four per-domain
ingest primitives are mocked (no Garmin / no real ingest); detection runs
against a seeded DuckDB keyed on ``date.fromisoformat(resolved_end)``.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from garmin_mcp.database.db_writer import GarminDBWriter
from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis
from garmin_mcp.ingest import catch_up
from garmin_mcp.ingest.catch_up import catch_up_ingest

# 2026-06-24 is a Wednesday; with the default Monday week start the current week
# begins 2026-06-22, so the last completed week begins 2026-06-15.
_BASE = "2026-06-24"
_EXPECTED_PENDING_START = "2026-06-15"

_ALL_DOMAIN_MOCKS = {
    "garmin_mcp.ingest.running_ingest.ingest_running_activities": {"ingested": 0},
    "garmin_mcp.ingest.weight_ingest.ingest_weight_range": {"ingested_days": 0},
    "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions": {"ingested": 0},
    "garmin_mcp.ingest.wellness_ingest.ingest_wellness_range": {"ingested_days": 0},
}


@pytest.mark.integration
def test_catch_up_appends_trend_pending_on_clean_run(temp_db_path: Path) -> None:
    """All domains succeed + empty trend_analyses -> trend_pending is attached."""
    GarminDBWriter(db_path=str(temp_db_path))

    with ExitStack() as stack:
        for target, value in _ALL_DOMAIN_MOCKS.items():
            stack.enter_context(patch(target, return_value=value))
        result = catch_up_ingest(end_date=_BASE, db_path=str(temp_db_path))

    assert "trend_pending" in result
    pending = result["trend_pending"]
    assert pending["granularity"] == "week"
    assert pending["period_start"] == _EXPECTED_PENDING_START


@pytest.mark.integration
def test_catch_up_omits_trend_pending_on_domain_error(temp_db_path: Path) -> None:
    """A raising domain runner -> status is not clean, so no trend_pending."""
    GarminDBWriter(db_path=str(temp_db_path))

    with (
        patch(
            "garmin_mcp.ingest.running_ingest.ingest_running_activities",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "garmin_mcp.ingest.weight_ingest.ingest_weight_range",
            return_value={"ingested_days": 0},
        ),
        patch(
            "garmin_mcp.ingest.strength_ingest.ingest_strength_sessions",
            return_value={"ingested": 0},
        ),
        patch(
            "garmin_mcp.ingest.wellness_ingest.ingest_wellness_range",
            return_value={"ingested_days": 0},
        ),
    ):
        result = catch_up_ingest(end_date=_BASE, db_path=str(temp_db_path))

    assert "error" in result["running"]
    assert "trend_pending" not in result


@pytest.mark.integration
def test_catch_up_omits_trend_pending_when_narrated(temp_db_path: Path) -> None:
    """An existing narration row for the last completed week -> no trend_pending."""
    GarminDBWriter(db_path=str(temp_db_path))
    insert_trend_analysis(
        {
            "granularity": "week",
            "period_start": _EXPECTED_PENDING_START,
            "period_end": "2026-06-21",
            "analysis_data": {"narrative": "既存"},
        },
        db_path=str(temp_db_path),
    )

    with ExitStack() as stack:
        for target, value in _ALL_DOMAIN_MOCKS.items():
            stack.enter_context(patch(target, return_value=value))
        result = catch_up_ingest(end_date=_BASE, db_path=str(temp_db_path))

    assert "trend_pending" not in result


@pytest.mark.unit
def test_detection_failure_does_not_fail_ingest() -> None:
    """A raising detector is swallowed: domain results return, no trend_pending."""

    def _ok_runner(window_start: str, window_end: str, db_path: str) -> dict:
        return {"ingested": 0}

    runners = dict.fromkeys(catch_up.DEFAULT_DOMAINS, _ok_runner)

    with (
        patch.object(catch_up, "_DOMAIN_RUNNERS", runners),
        patch.object(
            catch_up,
            "find_pending_trend_period",
            side_effect=RuntimeError("detector boom"),
        ),
    ):
        # start_date is explicit so no reader latest-date query touches disk;
        # the domain runners and detector are mocked -> a true no-I/O unit test.
        result = catch_up_ingest(
            start_date="2026-06-01",
            end_date=_BASE,
            db_path="/tmp/does-not-exist.duckdb",
        )

    for domain in catch_up.DEFAULT_DOMAINS:
        assert result[domain] == {"ingested": 0}
    assert "trend_pending" not in result
