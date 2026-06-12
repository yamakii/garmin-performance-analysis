"""Shared fixtures for garmin-web tests.

Fixture DBs are created in tmp_path with raw duckdb.connect() —
this is the documented exception to the get_connection()-only rule,
required because fixture creation needs write access to a new file.
"""

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

_CREATE_FORM_EVALUATIONS = """
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
    _CREATE_FORM_EVALUATIONS,
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
