"""Unit tests for garmin_web.queries.activities.list_activities."""

import json
from pathlib import Path

import duckdb
import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.activities import lead_sentence, list_activities

SUMMARY_ACTIVITY_ID = 9000000301

# The two weather columns are read by RunReportReader, which the list query
# calls for the newest rows' headline (#1254).
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


def _summary_db(tmp_path: Path, name: str, rows: list[tuple]) -> Path:
    """One activity plus the given (analysis_id, section_type, data, run_id)."""
    db_path = tmp_path / name
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_SECTION_ANALYSES)
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name,"
            " total_distance_km, total_time_seconds, avg_pace_seconds_per_km,"
            " avg_heart_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [SUMMARY_ACTIVITY_ID, "2025-10-09", "Morning Run", 5.66, 2186, 386.0, 144],
        )
        for analysis_id, section_type, data, run_id in rows:
            conn.execute(
                "INSERT INTO section_analyses (analysis_id, activity_id,"
                " activity_date, section_type, analysis_data, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    SUMMARY_ACTIVITY_ID,
                    "2025-10-09",
                    section_type,
                    data,
                    run_id,
                ],
            )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def summary_versions_db_path(tmp_path: Path) -> Path:
    """Two analysis runs for one activity; run 2 re-wrote the summary section."""
    old = json.dumps(
        {"star_rating": "★★★☆☆ 3.0/5.0", "summary": "旧。"}, ensure_ascii=False
    )
    new = json.dumps(
        {"star_rating": "★★★★☆ 4.2/5.0", "summary": "新しい要約。詳細。"},
        ensure_ascii=False,
    )
    return _summary_db(
        tmp_path,
        "test_garmin_web_summary_versions.duckdb",
        [
            (1, "summary", old, 1),
            (2, "split", json.dumps({"highlights": "s1"}), 1),
            (3, "summary", new, 2),
        ],
    )


@pytest.fixture
def run_note_db_path(tmp_path: Path) -> Path:
    """A legacy summary plus a newer coach review for the same activity."""
    summary = json.dumps(
        {"star_rating": "★★★★☆ 4.2/5.0", "summary": "旧の一文。続き。"},
        ensure_ascii=False,
    )
    run_note = json.dumps({"story": "新の一文。続き。"}, ensure_ascii=False)
    return _summary_db(
        tmp_path,
        "test_garmin_web_run_note.duckdb",
        [(1, "summary", summary, 1), (2, "run_note", run_note, 2)],
    )


@pytest.fixture
def broken_summary_db_path(tmp_path: Path) -> Path:
    """The latest summary section stored unparseable JSON."""
    return _summary_db(
        tmp_path,
        "test_garmin_web_broken_summary.duckdb",
        [(1, "summary", "{not json", 1)],
    )


@pytest.mark.unit
def test_list_activities_returns_all_sorted(fixture_db_path):
    with get_connection(fixture_db_path) as conn:
        activities = list_activities(conn)

    assert len(activities) == 2
    assert activities[0]["activity_date"] == "2025-10-09"
    assert activities[1]["activity_date"] == "2025-10-07"
    assert all(isinstance(a["activity_date"], str) for a in activities)


@pytest.mark.unit
def test_list_activities_date_filter(fixture_db_path):
    with get_connection(fixture_db_path) as conn:
        activities = list_activities(conn, from_date="2025-10-08")

    assert len(activities) == 1
    assert activities[0]["activity_date"] == "2025-10-09"


@pytest.mark.unit
def test_list_activities_empty_db(empty_db_path):
    with get_connection(empty_db_path) as conn:
        activities = list_activities(conn)

    assert activities == []


@pytest.mark.unit
def test_lead_sentence():
    assert lead_sentence("有酸素ベースとして安定。後半は…") == "有酸素ベースとして安定。"
    assert lead_sentence("句点なし") == "句点なし"
    assert lead_sentence("  余白あり。続き。 ") == "余白あり。"
    assert lead_sentence(None) is None
    assert lead_sentence("") is None
    assert lead_sentence("   ") is None


@pytest.mark.unit
def test_list_activities_story_lead_prefers_run_note(run_note_db_path):
    """The coach review wins over the legacy summary paragraph (#1254)."""
    with get_connection(run_note_db_path) as conn:
        activities = list_activities(conn)

    assert len(activities) == 1
    assert activities[0]["story_lead"] == "新の一文。"
    # The star rating is gone: single runs are no longer graded (#1247).
    assert "star_rating" not in activities[0]
    assert "summary_lead" not in activities[0]


@pytest.mark.unit
def test_list_activities_story_lead_falls_back_to_summary(summary_versions_db_path):
    """Without a run_note, the newest summary's opening sentence is used."""
    with get_connection(summary_versions_db_path) as conn:
        activities = list_activities(conn)

    assert len(activities) == 1
    assert activities[0]["story_lead"] == "新しい要約。"


@pytest.mark.unit
def test_list_activities_headline_from_run_report(summary_versions_db_path):
    """The headline is the run report's, not a second verdict of our own."""
    with get_connection(summary_versions_db_path) as conn:
        activities = list_activities(conn)

    # No weekly_prescriptions table in this fixture: the run was unprescribed.
    assert activities[0]["plan_label"] == "処方なし"
    assert activities[0]["flag_labels"] == []


@pytest.mark.unit
def test_list_activities_without_analysis_is_null(fixture_db_path):
    with get_connection(fixture_db_path) as conn:
        activities = list_activities(conn)

    # The join must not drop or reorder unanalysed activities.
    assert [a["activity_date"] for a in activities] == ["2025-10-09", "2025-10-07"]
    assert activities[0]["activity_name"] == "Morning Run"
    assert activities[0]["total_distance_km"] == 5.66
    assert activities[0]["avg_heart_rate"] == 144
    for activity in activities:
        assert activity["story_lead"] is None


@pytest.mark.unit
def test_list_activities_broken_summary_json(broken_summary_db_path):
    with get_connection(broken_summary_db_path) as conn:
        activities = list_activities(conn)

    assert len(activities) == 1
    assert activities[0]["story_lead"] is None
