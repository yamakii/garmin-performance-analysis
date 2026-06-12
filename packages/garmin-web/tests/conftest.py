"""Shared fixtures for garmin-web tests.

Fixture DBs are created in tmp_path with raw duckdb.connect() —
this is the documented exception to the get_connection()-only rule,
required because fixture creation needs write access to a new file.
"""

import json
from pathlib import Path

import duckdb
import pytest

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        activity_name VARCHAR,
        total_distance_km DOUBLE,
        total_time_seconds INTEGER,
        avg_pace_seconds_per_km DOUBLE,
        avg_heart_rate INTEGER
    )
"""

_FIXTURE_ROWS = [
    (9000000001, "2025-10-09", "Morning Run", 5.66, 2186, 386.0, 144),
    (9000000002, "2025-10-07", "Easy Run", 8.01, 2900, 362.0, 138),
]


@pytest.fixture
def fixture_db_path(tmp_path: Path) -> Path:
    """DuckDB with activities table and 2 rows (2025-10-09, 2025-10-07)."""
    db_path = tmp_path / "test_garmin_web.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            _FIXTURE_ROWS,
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_db_path(tmp_path: Path) -> Path:
    """DuckDB with empty activities table."""
    db_path = tmp_path / "test_garmin_web_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
    finally:
        conn.close()
    return db_path


# --- Trends fixtures (Issue #201) -------------------------------------------
# Column names mirror the production schema in
# garmin_mcp/database/db_writer.py (only columns used by trend queries).
# NOTE: form_evaluations DDL differs from the detail fixtures below because
# each fixture set creates its own database file with only the columns its
# queries touch.

_CREATE_VO2_MAX = """
    CREATE TABLE vo2_max (
        activity_id BIGINT PRIMARY KEY,
        precise_value DOUBLE,
        value DOUBLE,
        date DATE,
        category INTEGER
    )
"""

_CREATE_LACTATE_THRESHOLD = """
    CREATE TABLE lactate_threshold (
        activity_id BIGINT PRIMARY KEY,
        heart_rate INTEGER,
        speed_mps DOUBLE,
        date_hr TIMESTAMP
    )
"""

_CREATE_FORM_EVALUATIONS_TRENDS = """
    CREATE TABLE form_evaluations (
        eval_id INTEGER PRIMARY KEY,
        activity_id BIGINT UNIQUE,
        gct_delta_pct FLOAT,
        vo_delta_cm FLOAT,
        vr_delta_pct FLOAT,
        overall_score FLOAT
    )
"""

_CREATE_HR_EFFICIENCY = """
    CREATE TABLE hr_efficiency (
        activity_id BIGINT PRIMARY KEY,
        primary_zone VARCHAR,
        aerobic_efficiency VARCHAR,
        zone1_percentage DOUBLE,
        zone2_percentage DOUBLE,
        zone3_percentage DOUBLE,
        zone4_percentage DOUBLE,
        zone5_percentage DOUBLE
    )
"""

_TRENDS_TABLE_DDLS = [
    _CREATE_ACTIVITIES,
    _CREATE_VO2_MAX,
    _CREATE_LACTATE_THRESHOLD,
    _CREATE_FORM_EVALUATIONS_TRENDS,
    _CREATE_HR_EFFICIENCY,
]


def _create_trends_tables(conn: duckdb.DuckDBPyConnection) -> None:
    for ddl in _TRENDS_TABLE_DDLS:
        conn.execute(ddl)


@pytest.fixture
def trends_conn():
    """In-memory DuckDB with activities + 4 trend tables, no rows.

    Unit tests insert their own rows (activity_id band: 9000001xxx).
    """
    conn = duckdb.connect(":memory:")
    _create_trends_tables(conn)
    yield conn
    conn.close()


# (activity_id, date, name, distance_km, time_s, pace_s_per_km, avg_hr)
_TRENDS_ACTIVITY_ROWS = [
    (9000001001, "2025-10-06", "Run A", 10.0, 3600, 360.0, 140),
    (9000001002, "2025-10-09", "Run B", 5.0, 1800, 360.0, 145),
    (9000001003, "2025-10-13", "Run C", 8.0, 2400, 300.0, 150),
    (9000001004, "2025-11-03", "Run D", 7.0, 2100, 300.0, 148),
]


@pytest.fixture
def trends_db_path(tmp_path: Path) -> Path:
    """File DuckDB with activities + trend tables populated (9000001xxx)."""
    db_path = tmp_path / "test_garmin_web_trends.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        _create_trends_tables(conn)
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            _TRENDS_ACTIVITY_ROWS,
        )
        conn.executemany(
            "INSERT INTO vo2_max VALUES (?, ?, ?, ?, ?)",
            [
                (9000001001, 49.6, 50.0, "2025-10-06", 5),
                (9000001003, 50.1, 50.0, "2025-10-13", 5),
            ],
        )
        conn.execute(
            "INSERT INTO lactate_threshold VALUES (?, ?, ?, ?)",
            (9000001003, 168, 3.2, "2025-10-13 06:30:00"),
        )
        conn.executemany(
            "INSERT INTO form_evaluations VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 9000001001, 2.5, 0.4, 0.3, 4.2),
                (2, 9000001003, 1.8, 0.2, 0.1, 4.5),
            ],
        )
        conn.execute(
            "INSERT INTO hr_efficiency VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (9000001001, "Zone 2", "good", 10.0, 60.0, 20.0, 8.0, 2.0),
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_trends_db_path(tmp_path: Path) -> Path:
    """File DuckDB with activities + trend tables, all empty."""
    db_path = tmp_path / "test_garmin_web_trends_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        _create_trends_tables(conn)
    finally:
        conn.close()
    return db_path


# --- Detail page fixtures (Issue #199) ---------------------------------
# Reduced-column versions of the production schemas: queries use SELECT *
# and ORDER BY key columns only, so only representative columns are needed.

_CREATE_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE,
        pace_seconds_per_km DOUBLE,
        heart_rate INTEGER,
        cadence DOUBLE,
        power DOUBLE,
        ground_contact_time DOUBLE,
        vertical_oscillation DOUBLE,
        vertical_ratio DOUBLE,
        elevation_gain DOUBLE,
        elevation_loss DOUBLE,
        PRIMARY KEY (activity_id, split_index)
    )
"""

_CREATE_FORM_EFFICIENCY = """
    CREATE TABLE form_efficiency (
        activity_id BIGINT PRIMARY KEY,
        gct_average DOUBLE,
        vo_average DOUBLE,
        vr_average DOUBLE,
        gct_rating VARCHAR,
        vo_rating VARCHAR,
        vr_rating VARCHAR
    )
"""

_CREATE_HEART_RATE_ZONES = """
    CREATE TABLE heart_rate_zones (
        activity_id BIGINT,
        zone_number INTEGER,
        zone_low_boundary INTEGER,
        zone_high_boundary INTEGER,
        time_in_zone_seconds DOUBLE,
        zone_percentage DOUBLE,
        PRIMARY KEY (activity_id, zone_number)
    )
"""

_CREATE_PERFORMANCE_TRENDS = """
    CREATE TABLE performance_trends (
        activity_id BIGINT PRIMARY KEY,
        pace_consistency DOUBLE,
        hr_drift_percentage DOUBLE,
        fatigue_pattern VARCHAR
    )
"""

_CREATE_FORM_EVALUATIONS_DETAIL = """
    CREATE TABLE form_evaluations (
        eval_id INTEGER PRIMARY KEY,
        activity_id BIGINT UNIQUE,
        overall_score FLOAT,
        overall_star_rating VARCHAR,
        evaluated_at TIMESTAMP
    )
"""

_CREATE_TIME_SERIES_METRICS = """
    CREATE TABLE time_series_metrics (
        activity_id BIGINT NOT NULL,
        seq_no INTEGER NOT NULL,
        timestamp_s INTEGER NOT NULL,
        heart_rate DOUBLE,
        speed DOUBLE,
        cadence DOUBLE,
        PRIMARY KEY (activity_id, seq_no)
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
        agent_version VARCHAR
    )
"""

# Activity 9000000101: full data (5 splits, form_efficiency, 5 HR zones,
# performance_trends, form_evaluations, 2000 time-series rows, 5 sections).
# Activity 9000000102: partial data (2 splits, NO form_efficiency,
# 300 time-series rows, 5 sections — environment has broken JSON).
FULL_ACTIVITY_ID = 9000000101
PARTIAL_ACTIVITY_ID = 9000000102

_DETAIL_ACTIVITIES = [
    (FULL_ACTIVITY_ID, "2025-10-09", "Detail Run", 5.66, 2186, 386.0, 144),
    (PARTIAL_ACTIVITY_ID, "2025-10-07", "Partial Run", 2.0, 760, 380.0, 140),
]

# Inserted out of order on purpose: ORDER BY split_index must sort them.
_DETAIL_SPLITS = [
    (
        FULL_ACTIVITY_ID,
        3,
        1.0,
        385.0,
        385.0,
        146,
        172.0,
        250.0,
        248.0,
        7.8,
        8.1,
        4.0,
        3.0,
    ),
    (
        FULL_ACTIVITY_ID,
        1,
        1.0,
        390.0,
        390.0,
        138,
        170.0,
        245.0,
        250.0,
        7.9,
        8.2,
        5.0,
        2.0,
    ),
    (
        FULL_ACTIVITY_ID,
        5,
        0.66,
        250.0,
        379.0,
        150,
        173.0,
        255.0,
        246.0,
        7.7,
        8.0,
        1.0,
        1.0,
    ),
    (
        FULL_ACTIVITY_ID,
        2,
        1.0,
        388.0,
        388.0,
        142,
        171.0,
        248.0,
        249.0,
        7.8,
        8.1,
        3.0,
        4.0,
    ),
    (
        FULL_ACTIVITY_ID,
        4,
        1.0,
        382.0,
        382.0,
        148,
        172.0,
        252.0,
        247.0,
        7.7,
        8.0,
        2.0,
        2.0,
    ),
    (
        PARTIAL_ACTIVITY_ID,
        1,
        1.0,
        380.0,
        380.0,
        138,
        168.0,
        240.0,
        252.0,
        8.0,
        8.3,
        2.0,
        2.0,
    ),
    (
        PARTIAL_ACTIVITY_ID,
        2,
        1.0,
        379.0,
        379.0,
        141,
        169.0,
        242.0,
        251.0,
        7.9,
        8.2,
        1.0,
        1.0,
    ),
]

_DETAIL_HR_ZONES = [
    (FULL_ACTIVITY_ID, zone, 80 + zone * 20, 100 + zone * 20, 400.0, 20.0)
    for zone in range(1, 6)
]

_SECTION_TYPES = ["split", "phase", "efficiency", "environment", "summary"]


def _section_json(activity_id: int, section_type: str) -> str:
    return json.dumps(
        {
            "metadata": {
                "activity_id": str(activity_id),
                "date": "2025-10-09",
                "analyst": f"{section_type}-section-analyst",
                "version": "1.0",
                "timestamp": "2025-10-09T12:00:00+09:00",
            },
            "summary": f"{section_type} の分析テキスト",
        },
        ensure_ascii=False,
    )


@pytest.fixture
def detail_db_path(tmp_path: Path) -> Path:
    """DuckDB with all tables needed by the activity detail page."""
    db_path = tmp_path / "test_garmin_web_detail.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_SPLITS)
        conn.execute(_CREATE_FORM_EFFICIENCY)
        conn.execute(_CREATE_HEART_RATE_ZONES)
        conn.execute(_CREATE_PERFORMANCE_TRENDS)
        conn.execute(_CREATE_FORM_EVALUATIONS_DETAIL)
        conn.execute(_CREATE_TIME_SERIES_METRICS)
        conn.execute(_CREATE_SECTION_ANALYSES)

        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            _DETAIL_ACTIVITIES,
        )
        conn.executemany(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _DETAIL_SPLITS,
        )
        conn.execute(
            "INSERT INTO form_efficiency VALUES (?, ?, ?, ?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 248.0, 7.8, 8.1, "good", "good", "average"],
        )
        conn.executemany(
            "INSERT INTO heart_rate_zones VALUES (?, ?, ?, ?, ?, ?)",
            _DETAIL_HR_ZONES,
        )
        conn.execute(
            "INSERT INTO performance_trends VALUES (?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 4.2, 3.1, "stable"],
        )
        conn.execute(
            "INSERT INTO form_evaluations VALUES (?, ?, ?, ?, ?)",
            [1, FULL_ACTIVITY_ID, 4.1, "★★★★☆", "2025-10-09 12:00:00"],
        )

        # Time series: 2000 rows (full) / 300 rows (partial)
        conn.execute(
            "INSERT INTO time_series_metrics"
            f" SELECT {FULL_ACTIVITY_ID}, i, i, 140 + i % 20, 2.8, 170.0"
            " FROM range(2000) AS t(i)"
        )
        conn.execute(
            "INSERT INTO time_series_metrics"
            f" SELECT {PARTIAL_ACTIVITY_ID}, i, i, 135 + i % 10, 2.6, 168.0"
            " FROM range(300) AS t(i)"
        )

        # Sections: 5 valid for FULL; 4 valid + 1 broken (environment) for PARTIAL
        analysis_id = 1
        for section_type in _SECTION_TYPES:
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data, agent_name, agent_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    FULL_ACTIVITY_ID,
                    "2025-10-09",
                    section_type,
                    _section_json(FULL_ACTIVITY_ID, section_type),
                    f"{section_type}-section-analyst",
                    "1.0",
                ],
            )
            analysis_id += 1
        for section_type in _SECTION_TYPES:
            analysis_data = (
                '{"metadata": broken'
                if section_type == "environment"
                else _section_json(PARTIAL_ACTIVITY_ID, section_type)
            )
            conn.execute(
                "INSERT INTO section_analyses"
                " (analysis_id, activity_id, activity_date, section_type,"
                "  analysis_data, agent_name, agent_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    analysis_id,
                    PARTIAL_ACTIVITY_ID,
                    "2025-10-07",
                    section_type,
                    analysis_data,
                    f"{section_type}-section-analyst",
                    "1.0",
                ],
            )
            analysis_id += 1
    finally:
        conn.close()
    return db_path
