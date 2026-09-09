"""Integration tests for the trend_analyses inserter + reader (issue #789).

Covers ``insert_trend_analysis`` (append-only versioning + JSON serialization)
and ``TrendNarrationReader`` (latest-by-created_at, dedupe-per-period, all
versions). Uses the schema-initialized ``reader_db_path`` fixture, whose
``GarminDBWriter`` init runs migrations (including v16), so ``trend_analyses``
exists.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from garmin_mcp.database.inserters.trend_analyses import insert_trend_analysis
from garmin_mcp.database.readers.trends_narration import TrendNarrationReader


def _insert(db_path: str, period_start: str, narrative: str, **overrides) -> None:
    """Insert one trend record, spacing created_at so ordering is deterministic."""
    trend = {
        "granularity": "week",
        "period_start": period_start,
        "period_end": overrides.get("period_end", "2026-06-28"),
        "analysis_data": {"narrative": narrative},
        "agent_name": "trend-analyst",
        "agent_version": "1.0",
    }
    trend.update({k: v for k, v in overrides.items() if k != "period_end"})
    insert_trend_analysis(trend, db_path=db_path)
    # DuckDB CURRENT_TIMESTAMP has sub-second resolution; nudge so successive
    # versions get strictly increasing created_at for stable DESC ordering.
    time.sleep(0.01)


@pytest.mark.integration
def test_insert_appends_new_version(reader_db_path: Path) -> None:
    """Two inserts for the same period append two rows with distinct ids."""
    db_path = str(reader_db_path)
    _insert(db_path, "2026-06-22", "v1")
    _insert(db_path, "2026-06-22", "v2")

    reader = TrendNarrationReader(db_path=db_path)
    versions = reader.list_trend_analysis_versions("week", "2026-06-22")

    assert len(versions) == 2
    ids = {v["analysis_id"] for v in versions}
    assert len(ids) == 2


@pytest.mark.integration
def test_insert_serializes_analysis_data(reader_db_path: Path) -> None:
    """analysis_data round-trips: stored as JSON, read back as a dict."""
    db_path = str(reader_db_path)
    insert_trend_analysis(
        {
            "granularity": "week",
            "period_start": "2026-06-22",
            "period_end": "2026-06-28",
            "analysis_data": {"narrative": "順調"},
            "agent_name": "trend-analyst",
            "agent_version": "1.0",
        },
        db_path=db_path,
    )

    reader = TrendNarrationReader(db_path=db_path)
    result = reader.get_trend_analysis("week", "2026-06-22")

    assert result is not None
    assert result["analysis_data"]["narrative"] == "順調"


@pytest.mark.integration
def test_get_returns_latest_by_created_at(reader_db_path: Path) -> None:
    """get_trend_analysis returns the newest version for a period."""
    db_path = str(reader_db_path)
    _insert(db_path, "2026-06-22", "v1")
    _insert(db_path, "2026-06-22", "v2")

    reader = TrendNarrationReader(db_path=db_path)
    result = reader.get_trend_analysis("week", "2026-06-22")

    assert result is not None
    assert result["analysis_data"]["narrative"] == "v2"


@pytest.mark.integration
def test_get_returns_none_when_missing(reader_db_path: Path) -> None:
    """get_trend_analysis returns None for an empty table."""
    reader = TrendNarrationReader(db_path=str(reader_db_path))
    assert reader.get_trend_analysis("week", "2026-06-22") is None


@pytest.mark.integration
def test_list_dedupes_to_latest_per_period(reader_db_path: Path) -> None:
    """list_trend_analyses yields one row per period (latest), period DESC."""
    db_path = str(reader_db_path)
    _insert(db_path, "2026-06-15", "A-v1", period_end="2026-06-21")
    _insert(db_path, "2026-06-15", "A-v2", period_end="2026-06-21")
    _insert(db_path, "2026-06-22", "B-v1")

    reader = TrendNarrationReader(db_path=db_path)
    rows = reader.list_trend_analyses("week")

    assert len(rows) == 2
    # period_start DESC: the newer week (2026-06-22) comes first.
    assert rows[0]["period_start"] == "2026-06-22"
    assert rows[1]["period_start"] == "2026-06-15"
    # Week A dedupes to its latest version.
    assert rows[1]["analysis_data"]["narrative"] == "A-v2"


@pytest.mark.integration
def test_list_versions_returns_all(reader_db_path: Path) -> None:
    """list_trend_analysis_versions returns every version, created_at DESC."""
    db_path = str(reader_db_path)
    _insert(db_path, "2026-06-22", "v1")
    _insert(db_path, "2026-06-22", "v2")
    _insert(db_path, "2026-06-22", "v3")

    reader = TrendNarrationReader(db_path=db_path)
    versions = reader.list_trend_analysis_versions("week", "2026-06-22")

    assert len(versions) == 3
    narratives = [v["analysis_data"]["narrative"] for v in versions]
    assert narratives == ["v3", "v2", "v1"]
