"""Unit tests for garmin_web.queries.sections.get_sections."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.sections import get_sections

FULL_ACTIVITY_ID = 9000000101  # 5 valid sections
PARTIAL_ACTIVITY_ID = 9000000102  # 4 valid + broken "environment" section

SECTION_TYPES = {"split", "phase", "efficiency", "environment", "summary"}


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
