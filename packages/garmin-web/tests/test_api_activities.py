"""API tests for GET /api/activities."""

import json
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from garmin_web.app import create_app
from garmin_web.queries.activities import RECENT_REPORT_ROWS

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        activity_name VARCHAR,
        total_distance_km DOUBLE,
        total_time_seconds INTEGER,
        avg_pace_seconds_per_km DOUBLE,
        avg_heart_rate INTEGER,
        temp_celsius DOUBLE,
        relative_humidity_percent DOUBLE,
        wind_speed_kmh DOUBLE
    )
"""

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


def _analysed_db(tmp_path: Path, name: str, sections: list[tuple]) -> Path:
    """12 dated activities plus the given section rows.

    ``sections`` items are ``(analysis_id, activity_id, section_type, data,
    run_id)``. Twelve runs is two more than ``RECENT_REPORT_ROWS``, so the
    same fixture pins both the headline cutoff and the story fallbacks.
    """
    db_path = tmp_path / name
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_SECTION_ANALYSES)
        for index in range(12):
            conn.execute(
                "INSERT INTO activities (activity_id, activity_date,"
                " activity_name, total_distance_km, total_time_seconds,"
                " avg_pace_seconds_per_km, avg_heart_rate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    9000000400 + index,
                    f"2026-03-{index + 1:02d}",
                    "イージーラン",
                    8.0,
                    2900,
                    362.0,
                    138,
                ],
            )
        for analysis_id, activity_id, section_type, data, run_id in sections:
            conn.execute(
                "INSERT INTO section_analyses (analysis_id, activity_id,"
                " activity_date, section_type, analysis_data, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    activity_id,
                    "2026-03-12",
                    section_type,
                    data,
                    run_id,
                ],
            )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def analysed_list_db_path(tmp_path: Path) -> Path:
    """The newest run has both a legacy summary and a newer coach review."""
    newest = 9000000411
    summary = json.dumps(
        {"star_rating": "★★★★☆ 4.2/5.0", "summary": "旧の一文。続き。"},
        ensure_ascii=False,
    )
    run_note = json.dumps({"story": "新の一文。続き。"}, ensure_ascii=False)
    return _analysed_db(
        tmp_path,
        "test_garmin_web_list_run_note.duckdb",
        [
            (1, newest, "summary", summary, 1),
            (2, newest, "run_note", run_note, 2),
            # The second-newest run was only ever analysed the old way.
            (3, 9000000410, "summary", summary, 1),
        ],
    )


@pytest.mark.integration
def test_api_activities_returns_200(fixture_db_path):
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    for item in payload:
        assert "activity_id" in item
        assert "activity_date" in item
        assert "total_distance_km" in item


@pytest.mark.integration
def test_activities_rows_have_headline_fields_not_stars(fixture_db_path):
    """Single runs are no longer graded: the row carries the headline (#1247)."""
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    for item in response.json():
        assert "plan_label" in item
        assert item["flag_labels"] == []
        assert "story_lead" in item
        assert "star_rating" not in item
        assert "summary_lead" not in item


@pytest.mark.integration
def test_story_lead_prefers_run_note(analysed_list_db_path):
    """The coach review's first sentence wins over the legacy summary's."""
    client = TestClient(create_app(db_path=analysed_list_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    assert response.json()[0]["story_lead"] == "新の一文。"


@pytest.mark.integration
def test_story_lead_falls_back_to_legacy_summary(analysed_list_db_path):
    """A run analysed before run_note existed still gets its opening sentence."""
    client = TestClient(create_app(db_path=analysed_list_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    assert response.json()[1]["story_lead"] == "旧の一文。"


@pytest.mark.integration
def test_headline_only_for_recent_rows(analysed_list_db_path):
    """Only the newest rows pay for a run report; older ones stay empty."""
    client = TestClient(create_app(db_path=analysed_list_db_path))
    response = client.get("/api/activities")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 12
    for item in payload[:RECENT_REPORT_ROWS]:
        assert item["plan_label"] == "処方なし"
    for item in payload[RECENT_REPORT_ROWS:]:
        assert item["plan_label"] is None
        assert item["flag_labels"] == []


@pytest.mark.unit
def test_api_activities_invalid_date_422(fixture_db_path):
    client = TestClient(create_app(db_path=fixture_db_path))
    response = client.get("/api/activities", params={"from": "not-a-date"})

    assert response.status_code == 422
