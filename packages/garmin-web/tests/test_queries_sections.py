"""Unit tests for garmin_web.queries.sections."""

import json
from pathlib import Path

import duckdb
import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.sections import get_sections, list_section_versions

FULL_ACTIVITY_ID = 9000000101  # 5 valid sections
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
        agent_version VARCHAR
    )
"""


@pytest.fixture
def versioned_sections_db_path(tmp_path: Path) -> Path:
    """DuckDB with two analysis batches for one activity.

    Batch 1 (12:00): summary v1 + split v1. Batch 2 (13:00): summary v2.
    """
    db_path = tmp_path / "test_garmin_web_versioned_sections.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_SECTION_ANALYSES)
        rows = [
            (1, "summary", json.dumps({"summary": "v1"}), OLD_STAMP),
            (2, "split", json.dumps({"highlights": "s1"}), OLD_STAMP),
            (3, "summary", json.dumps({"summary": "v2"}), NEW_STAMP),
        ]
        for analysis_id, section_type, data, stamp in rows:
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    VERSIONED_ACTIVITY_ID,
                    "2025-10-09",
                    section_type,
                    data,
                    stamp,
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
def test_sections_default_returns_latest(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        sections = get_sections(conn, VERSIONED_ACTIVITY_ID)

    # summary resolves to the newest version; split keeps its only version.
    assert sections["summary"]["data"]["summary"] == "v2"
    assert sections["split"]["data"]["highlights"] == "s1"


@pytest.mark.unit
def test_sections_pinned_created_at(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        sections = get_sections(conn, VERSIONED_ACTIVITY_ID, created_at=OLD_STAMP)

    # Pinned to the older batch: summary returns its v1 payload.
    assert sections["summary"]["data"]["summary"] == "v1"
    assert sections["split"]["data"]["highlights"] == "s1"


@pytest.mark.unit
def test_sections_versions_lists_batches(versioned_sections_db_path):
    with get_connection(versioned_sections_db_path) as conn:
        versions = list_section_versions(conn, VERSIONED_ACTIVITY_ID)

    # Two batches, newest first.
    assert len(versions) == 2
    assert versions[0]["created_at"] == NEW_STAMP
    assert versions[0]["section_types"] == ["summary"]
    assert versions[1]["created_at"] == OLD_STAMP
    assert versions[1]["section_types"] == ["split", "summary"]
