"""Unit tests for garmin_web.queries.sections."""

import json
from pathlib import Path

import duckdb
import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.sections import get_sections, list_section_versions

FULL_ACTIVITY_ID = 9000000101  # 5 valid sections, one run (run_id 1)
PARTIAL_ACTIVITY_ID = 9000000102  # 4 valid + broken "environment" section

SECTION_TYPES = {"split", "phase", "efficiency", "environment", "summary"}

VERSIONED_ACTIVITY_ID = 9000000201
OLD_STAMP = "2025-10-09 12:00:00"
NEW_STAMP = "2025-10-09 13:00:00"

_CREATE_SECTION_ANALYSES = """
    CREATE TABLE section_analyses (
        analysis_id INTEGER PRIMARY KEY,
        activity_id BIGINT NOT NULL,
        activity_date DATE NOT NULL,
        section_type VARCHAR NOT NULL,
        analysis_data VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        agent_name VARCHAR,
        agent_version VARCHAR,
        run_id BIGINT
    )
"""


@pytest.fixture
def versioned_sections_db_path(tmp_path: Path) -> Path:
    """DuckDB with two analysis runs for one activity.

    Run 1 (run_id 1, 12:00): summary v1 + split v1. Run 2 (run_id 2, 13:00):
    a partial re-analysis of summary only (summary v2).
    """
    db_path = tmp_path / "test_garmin_web_versioned_sections.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_SECTION_ANALYSES)
        rows = [
            (1, "summary", json.dumps({"summary": "v1"}), OLD_STAMP, 1),
            (2, "split", json.dumps({"highlights": "s1"}), OLD_STAMP, 1),
            (3, "summary", json.dumps({"summary": "v2"}), NEW_STAMP, 2),
        ]
        for analysis_id, section_type, data, stamp, run_id in rows:
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data, created_at, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    VERSIONED_ACTIVITY_ID,
                    "2025-10-09",
                    section_type,
                    data,
                    stamp,
                    run_id,
                ],
            )
    finally:
        conn.close()
    return db_path


@pytest.mark.unit
def test_sections_parses_json_per_type(detail_db_path):
    with get_connection(detail_db_path) as conn:
        sections = get_sections(conn, FULL_ACTIVITY_ID)

    assert set(sections.keys()) == SECTION_TYPES
    for section_type, section in sections.items():
        assert section["parse_error"] is False, section_type
        assert isinstance(section["data"], dict)
        assert section["data"]["metadata"]["activity_id"] == str(FULL_ACTIVITY_ID)
        assert section["raw"] is None


@pytest.mark.unit
def test_sections_invalid_json_fallback(detail_db_path):
    with get_connection(detail_db_path) as conn:
        sections = get_sections(conn, PARTIAL_ACTIVITY_ID)

    assert set(sections.keys()) == SECTION_TYPES

    broken = sections["environment"]
    assert broken["parse_error"] is True
    assert broken["data"] is None
    assert broken["raw"] == '{"metadata": broken'

    for section_type in SECTION_TYPES - {"environment"}:
        section = sections[section_type]
        assert section["parse_error"] is False, section_type
        assert isinstance(section["data"], dict)
        assert section["raw"] is None


@pytest.mark.unit
def test_versions_group_by_run_one_run_one_version(detail_db_path):
    """A single analysis run of 5 sections is one version, not five (#776)."""
    with get_connection(detail_db_path) as conn:
        versions = list_section_versions(conn, FULL_ACTIVITY_ID)

    assert len(versions) == 1
    assert versions[0]["run_id"] == 1
    assert sorted(versions[0]["section_types"]) == sorted(SECTION_TYPES)


@pytest.mark.unit
def test_sections_default_returns_latest(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        sections = get_sections(conn, VERSIONED_ACTIVITY_ID)

    # summary resolves to the newest run; split keeps its only version.
    assert sections["summary"]["data"]["summary"] == "v2"
    assert sections["split"]["data"]["highlights"] == "s1"


@pytest.mark.unit
def test_sections_pinned_by_run_id(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        sections = get_sections(conn, VERSIONED_ACTIVITY_ID, run_id=1)

    # Pinned to run 1: summary returns its v1 payload; split is carried over.
    assert sections["summary"]["data"]["summary"] == "v1"
    assert sections["split"]["data"]["highlights"] == "s1"


@pytest.mark.unit
def test_sections_versions_lists_runs(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        versions = list_section_versions(conn, VERSIONED_ACTIVITY_ID)

    # Two runs, newest (run_id 2) first. Each run lists only what it wrote.
    assert len(versions) == 2
    assert versions[0]["run_id"] == 2
    assert versions[0]["created_at"] == NEW_STAMP
    assert versions[0]["section_types"] == ["summary"]
    assert versions[1]["run_id"] == 1
    assert versions[1]["created_at"] == OLD_STAMP
    assert versions[1]["section_types"] == ["split", "summary"]


@pytest.mark.unit
def test_versions_empty_when_no_sections(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        versions = list_section_versions(conn, 123456789)

    assert versions == []
