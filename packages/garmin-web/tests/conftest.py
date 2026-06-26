"""Shared fixtures for garmin-web tests.

Fixture DBs are created in tmp_path with raw duckdb.connect() —
this is the documented exception to the get_connection()-only rule,
required because fixture creation needs write access to a new file.
"""

import datetime as _dt
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


# --- Objective fitness curve fixtures (Issue #564) ---------------------------
# get_objective_fitness_trend reads `splits` (km-unit distance + duration) +
# `activities` (date) + `vo2_max` (value/date). The 1km laps feed best-effort
# extraction (km->m conversion in the query) and the latest VO2max anchors the
# optimism gap.
_CREATE_OBJ_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE
    )
"""


@pytest.fixture
def objective_fitness_db_path(tmp_path: Path) -> Path:
    """File DuckDB with two km-unit runs + Garmin VO2max rows."""
    db_path = tmp_path / "test_garmin_web_objective_fitness.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_OBJ_SPLITS)
        conn.execute(_CREATE_VO2_MAX)
        conn.executemany(
            "INSERT INTO activities ("
            "activity_id, activity_date, activity_name, total_distance_km,"
            " total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (9200001001, "2026-04-01", "Run A", 10.0, 3700, 370.0, 150),
                (9200001002, "2026-05-01", "Run B", 6.0, 2160, 360.0, 152),
            ],
        )
        run1 = [(9200001001, i, 1.0, 370.0) for i in range(10)]
        run2 = [(9200001002, i, 1.0, 360.0) for i in range(6)]
        conn.executemany("INSERT INTO splits VALUES (?, ?, ?, ?)", run1 + run2)
        conn.executemany(
            "INSERT INTO vo2_max (activity_id, precise_value, value, date, category)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (9200001001, 48.0, 48.0, "2026-04-01", 5),
                (9200001002, 49.0, 49.0, "2026-05-01", 5),
            ],
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_objective_fitness_db_path(tmp_path: Path) -> Path:
    """File DuckDB with empty activities + splits + vo2_max tables."""
    db_path = tmp_path / "test_garmin_web_objective_fitness_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_OBJ_SPLITS)
        conn.execute(_CREATE_VO2_MAX)
    finally:
        conn.close()
    return db_path


# --- Detail page fixtures (Issue #199) ---------------------------------
# Full production schemas (mirroring garmin_mcp/database/db_writer.py and the
# applied migrations) so the explicit-column queries in queries/detail.py
# (Issue #369) resolve every column. Column order matches the live database
# (PRAGMA table_info order), i.e. what the previous ``SELECT *`` returned.

_CREATE_DETAIL_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        activity_name VARCHAR,
        start_time_local TIMESTAMP,
        start_time_gmt TIMESTAMP,
        location_name VARCHAR,
        total_distance_km DOUBLE,
        total_time_seconds INTEGER,
        avg_speed_ms DOUBLE,
        avg_pace_seconds_per_km DOUBLE,
        avg_heart_rate INTEGER,
        max_heart_rate INTEGER,
        temp_celsius DOUBLE,
        relative_humidity_percent DOUBLE,
        wind_speed_kmh DOUBLE,
        wind_direction VARCHAR,
        gear_type VARCHAR,
        gear_model VARCHAR,
        base_weight_kg DOUBLE,
        body_mass_kg DOUBLE
    )
"""

_CREATE_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE,
        start_time_gmt VARCHAR,
        start_time_s INTEGER,
        end_time_s INTEGER,
        intensity_type VARCHAR,
        role_phase VARCHAR,
        pace_str VARCHAR,
        pace_seconds_per_km DOUBLE,
        heart_rate INTEGER,
        hr_zone VARCHAR,
        cadence DOUBLE,
        cadence_rating VARCHAR,
        power DOUBLE,
        power_efficiency VARCHAR,
        stride_length DOUBLE,
        ground_contact_time DOUBLE,
        vertical_oscillation DOUBLE,
        vertical_ratio DOUBLE,
        elevation_gain DOUBLE,
        elevation_loss DOUBLE,
        terrain_type VARCHAR,
        environmental_conditions VARCHAR,
        wind_impact VARCHAR,
        temp_impact VARCHAR,
        environmental_impact VARCHAR,
        max_heart_rate INTEGER,
        max_cadence DOUBLE,
        max_power DOUBLE,
        normalized_power DOUBLE,
        average_speed DOUBLE,
        grade_adjusted_speed DOUBLE,
        PRIMARY KEY (activity_id, split_index)
    )
"""

_CREATE_FORM_EFFICIENCY = """
    CREATE TABLE form_efficiency (
        activity_id BIGINT PRIMARY KEY,
        gct_average DOUBLE,
        gct_min DOUBLE,
        gct_max DOUBLE,
        gct_std DOUBLE,
        gct_variability DOUBLE,
        gct_rating VARCHAR,
        gct_evaluation VARCHAR,
        vo_average DOUBLE,
        vo_min DOUBLE,
        vo_max DOUBLE,
        vo_std DOUBLE,
        vo_trend VARCHAR,
        vo_rating VARCHAR,
        vo_evaluation VARCHAR,
        vr_average DOUBLE,
        vr_min DOUBLE,
        vr_max DOUBLE,
        vr_std DOUBLE,
        vr_rating VARCHAR,
        vr_evaluation VARCHAR
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
        cadence_consistency VARCHAR,
        fatigue_pattern VARCHAR,
        warmup_splits VARCHAR,
        warmup_avg_pace_seconds_per_km DOUBLE,
        warmup_avg_pace_str VARCHAR,
        warmup_avg_hr DOUBLE,
        warmup_avg_cadence DOUBLE,
        warmup_avg_power DOUBLE,
        warmup_evaluation VARCHAR,
        run_splits VARCHAR,
        run_avg_pace_seconds_per_km DOUBLE,
        run_avg_pace_str VARCHAR,
        run_avg_hr DOUBLE,
        run_avg_cadence DOUBLE,
        run_avg_power DOUBLE,
        run_evaluation VARCHAR,
        recovery_splits VARCHAR,
        recovery_avg_pace_seconds_per_km DOUBLE,
        recovery_avg_pace_str VARCHAR,
        recovery_avg_hr DOUBLE,
        recovery_avg_cadence DOUBLE,
        recovery_avg_power DOUBLE,
        recovery_evaluation VARCHAR,
        cooldown_splits VARCHAR,
        cooldown_avg_pace_seconds_per_km DOUBLE,
        cooldown_avg_pace_str VARCHAR,
        cooldown_avg_hr DOUBLE,
        cooldown_avg_cadence DOUBLE,
        cooldown_avg_power DOUBLE,
        cooldown_evaluation VARCHAR
    )
"""

# Live column order: cadence_* columns and integrated_score/training_mode were
# appended by migrations, so they follow evaluated_at (not the CREATE TABLE
# textual order in db_writer.py).
_CREATE_FORM_EVALUATIONS_DETAIL = """
    CREATE TABLE form_evaluations (
        eval_id INTEGER PRIMARY KEY,
        activity_id BIGINT UNIQUE,
        gct_ms_expected FLOAT,
        vo_cm_expected FLOAT,
        vr_pct_expected FLOAT,
        gct_ms_actual FLOAT,
        vo_cm_actual FLOAT,
        vr_pct_actual FLOAT,
        gct_delta_pct FLOAT,
        vo_delta_cm FLOAT,
        vr_delta_pct FLOAT,
        gct_penalty FLOAT,
        gct_star_rating VARCHAR,
        gct_score FLOAT,
        gct_needs_improvement BOOLEAN,
        gct_evaluation_text TEXT,
        vo_penalty FLOAT,
        vo_star_rating VARCHAR,
        vo_score FLOAT,
        vo_needs_improvement BOOLEAN,
        vo_evaluation_text TEXT,
        vr_penalty FLOAT,
        vr_star_rating VARCHAR,
        vr_score FLOAT,
        vr_needs_improvement BOOLEAN,
        vr_evaluation_text TEXT,
        cadence_actual FLOAT,
        cadence_minimum INTEGER DEFAULT 180,
        cadence_achieved BOOLEAN,
        overall_score FLOAT,
        overall_star_rating VARCHAR,
        power_avg_w FLOAT,
        power_wkg FLOAT,
        speed_actual_mps FLOAT,
        speed_expected_mps FLOAT,
        power_efficiency_score FLOAT,
        power_efficiency_rating VARCHAR,
        power_efficiency_needs_improvement BOOLEAN,
        integrated_score DOUBLE,
        training_mode VARCHAR,
        evaluated_at TIMESTAMP,
        cadence_expected DOUBLE,
        cadence_delta_pct DOUBLE,
        cadence_star_rating VARCHAR,
        cadence_score DOUBLE,
        cadence_needs_improvement BOOLEAN,
        cadence_evaluation_text VARCHAR
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
        latitude DOUBLE,
        longitude DOUBLE,
        ground_contact_time DOUBLE,
        vertical_oscillation DOUBLE,
        vertical_ratio DOUBLE,
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


@pytest.fixture
def track_conn():
    """In-memory DuckDB with time_series_metrics table, no rows.

    Track unit tests insert their own rows (activity_id band: 9000002xxx).
    Column order: activity_id, seq_no, timestamp_s, heart_rate, speed,
    cadence, latitude, longitude.
    """
    conn = duckdb.connect(":memory:")
    conn.execute(_CREATE_TIME_SERIES_METRICS)
    yield conn
    conn.close()


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


# Real-schema payloads per section type (Spike #198: key occurrence table).
# Keys present in 100% of production rows are included for each type.
_SECTION_PAYLOADS: dict[str, dict] = {
    "split": {
        "highlights": "**2km地点**で最速ペース 6:19/km を記録しました。",
        "analyses": {
            "split_1": "入りの1kmは 6:30/km と抑えた立ち上がりでした。",
            "split_2": "ペースが 6:19/km まで上がり心拍も安定しています。",
        },
    },
    "phase": {
        "warmup_evaluation": "心拍 130bpm 台で適切なウォームアップでした。",
        "run_evaluation": "メインランは 6:26/km で安定していました。",
        "cooldown_evaluation": "最後の 0.6km で心拍を 120bpm 台へ落とせています。",
        "evaluation_criteria": "aerobic_base 基準（HR Zone 2 中心）で評価しています。",
    },
    "efficiency": {
        "efficiency": "GCT 248ms、上下動 7.8cm とフォーム効率は良好です。",
        "evaluation": "Zone 2 滞在率 60% で有酸素ベースに合致しています。",
        "form_trend": "後半もフォーム指標の劣化は見られません。",
    },
    "environment": {
        "environmental": "気温 18°C・無風でコンディションは良好でした。",
    },
    "summary": {
        "star_rating": "★★★★☆ 4.2/5.0",
        "summary": "有酸素ベースとして安定した良いランでした。",
        "key_strengths": ["心拍の安定（平均144bpm）", "ケイデンス維持"],
        "improvement_areas": ["後半のペース低下", "ウォームアップ不足"],
        "recommendations": "次回は HR 135-145 を維持してイージーランを実施しましょう。",
    },
}


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
            **_SECTION_PAYLOADS[section_type],
        },
        ensure_ascii=False,
    )


@pytest.fixture
def detail_db_path(tmp_path: Path) -> Path:
    """DuckDB with all tables needed by the activity detail page."""
    db_path = tmp_path / "test_garmin_web_detail.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_DETAIL_ACTIVITIES)
        conn.execute(_CREATE_SPLITS)
        conn.execute(_CREATE_FORM_EFFICIENCY)
        conn.execute(_CREATE_HEART_RATE_ZONES)
        conn.execute(_CREATE_PERFORMANCE_TRENDS)
        conn.execute(_CREATE_FORM_EVALUATIONS_DETAIL)
        conn.execute(_CREATE_VO2_MAX)
        conn.execute(_CREATE_LACTATE_THRESHOLD)
        conn.execute(_CREATE_TIME_SERIES_METRICS)
        conn.execute(_CREATE_SECTION_ANALYSES)

        # Insert into the same 7 representative columns the reduced fixtures
        # used; the remaining production columns stay NULL.
        conn.executemany(
            "INSERT INTO activities ("
            "activity_id, activity_date, activity_name, total_distance_km,"
            " total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            _DETAIL_ACTIVITIES,
        )
        conn.executemany(
            "INSERT INTO splits ("
            "activity_id, split_index, distance, duration_seconds,"
            " pace_seconds_per_km, heart_rate, cadence, power,"
            " ground_contact_time, vertical_oscillation, vertical_ratio,"
            " elevation_gain, elevation_loss"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _DETAIL_SPLITS,
        )
        conn.execute(
            "INSERT INTO form_efficiency ("
            "activity_id, gct_average, vo_average, vr_average, gct_rating,"
            " vo_rating, vr_rating"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 248.0, 7.8, 8.1, "good", "good", "average"],
        )
        conn.executemany(
            "INSERT INTO heart_rate_zones VALUES (?, ?, ?, ?, ?, ?)",
            _DETAIL_HR_ZONES,
        )
        conn.execute(
            "INSERT INTO performance_trends ("
            "activity_id, pace_consistency, hr_drift_percentage, fatigue_pattern"
            ") VALUES (?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 4.2, 3.1, "stable"],
        )
        conn.execute(
            "INSERT INTO form_evaluations ("
            "eval_id, activity_id, overall_score, overall_star_rating,"
            " evaluated_at"
            ") VALUES (?, ?, ?, ?, ?)",
            [1, FULL_ACTIVITY_ID, 4.1, "★★★★☆", "2025-10-09 12:00:00"],
        )
        # Physiology rows for the FULL activity only (PARTIAL has none).
        conn.execute(
            "INSERT INTO vo2_max VALUES (?, ?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 49.6, 50.0, "2025-10-09", 5],
        )
        conn.execute(
            "INSERT INTO lactate_threshold VALUES (?, ?, ?, ?)",
            [FULL_ACTIVITY_ID, 168, 3.2, "2025-10-09 06:30:00"],
        )

        # Time series: 2000 rows with GPS (full) / 300 rows without GPS
        # (partial, simulating an indoor run).
        conn.execute(
            "INSERT INTO time_series_metrics"
            f" SELECT {FULL_ACTIVITY_ID}, i, i, 140 + i % 20, 2.8, 170.0,"
            " 35.6 + i * 1e-5, 139.7 + i * 1e-5, NULL, NULL, NULL"
            " FROM range(2000) AS t(i)"
        )
        conn.execute(
            "INSERT INTO time_series_metrics"
            f" SELECT {PARTIAL_ACTIVITY_ID}, i, i, 135 + i % 10, 2.6, 168.0,"
            " NULL, NULL, NULL, NULL, NULL"
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


# --- Goal page fixtures (Issue #282) -----------------------------------
# Mirror the athlete-centric schema in
# garmin_mcp/database/migrations/add_athlete_tables.py (only the columns the
# goal query reads). The Web app is read-only; data is written here directly.

_CREATE_ATHLETE_PROFILE = """
    CREATE TABLE athlete_profile (
        user_id VARCHAR PRIMARY KEY DEFAULT 'default',
        current_focus VARCHAR,
        focus_notes VARCHAR,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_CREATE_ATHLETE_GOALS = """
    CREATE TABLE athlete_goals (
        goal_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        race_name VARCHAR NOT NULL,
        race_date DATE,
        priority VARCHAR,
        goal_type VARCHAR,
        distance_km DOUBLE,
        target_time_seconds INTEGER,
        status VARCHAR DEFAULT 'active',
        notes VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_CREATE_SEASON_RETROSPECTIVES = """
    CREATE TABLE season_retrospectives (
        retro_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        season_label VARCHAR,
        period_start DATE,
        period_end DATE,
        narrative VARCHAR,
        key_learnings VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

_GOAL_TABLE_DDLS = [
    _CREATE_ATHLETE_PROFILE,
    _CREATE_ATHLETE_GOALS,
    _CREATE_SEASON_RETROSPECTIVES,
]


def _create_goal_tables(conn: duckdb.DuckDBPyConnection) -> None:
    for ddl in _GOAL_TABLE_DDLS:
        conn.execute(ddl)


@pytest.fixture
def goal_db_path(tmp_path: Path) -> Path:
    """DuckDB with athlete tables: 1 profile, 2 goals, 1 retrospective."""
    db_path = tmp_path / "test_garmin_web_goal.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        _create_goal_tables(conn)
        conn.execute(
            "INSERT INTO athlete_profile "
            "(user_id, current_focus, focus_notes, updated_at) "
            "VALUES (?, ?, ?, ?)",
            [
                "default",
                "サブ4達成に向けた持久力強化",
                "週末ロング走を軸に有酸素ベースを底上げ",
                "2026-06-14 09:00:00",
            ],
        )
        conn.executemany(
            "INSERT INTO athlete_goals ("
            "goal_id, user_id, race_name, race_date, priority, goal_type,"
            " distance_km, target_time_seconds, status, notes"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    1,
                    "default",
                    "つくばマラソン",
                    "2026-11-22",
                    "A",
                    "marathon",
                    42.195,
                    16200,  # 4:30:00
                    "active",
                    "メインターゲット",
                ),
                (
                    2,
                    "default",
                    "ハーフマラソン大会",
                    None,  # 日付未定
                    "B",
                    "half",
                    21.0975,
                    7200,  # 2:00:00
                    "active",
                    "調整レース",
                ),
            ],
        )
        conn.execute(
            "INSERT INTO season_retrospectives ("
            "retro_id, user_id, season_label, period_start, period_end,"
            " narrative, key_learnings"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                1,
                "default",
                "2025秋シーズン",
                "2025-09-01",
                "2025-12-31",
                "故障なく走り込めた一方、後半の失速が課題でした。",
                "ロング走でのペース管理を重視する",
            ],
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_goal_db_path(tmp_path: Path) -> Path:
    """DuckDB with empty athlete tables (no profile / goals / retrospectives)."""
    db_path = tmp_path / "test_garmin_web_goal_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        _create_goal_tables(conn)
    finally:
        conn.close()
    return db_path


# --- Weekly review page fixtures (Issue #283) --------------------------
# Mirror the weekly_reviews schema in
# garmin_mcp/database/migrations/add_athlete_tables.py (review_data is stored
# as a JSON VARCHAR). The Web app is read-only; data is written here directly.

_CREATE_WEEKLY_REVIEWS = """
    CREATE TABLE weekly_reviews (
        review_id INTEGER PRIMARY KEY,
        user_id VARCHAR DEFAULT 'default',
        week_start_date DATE NOT NULL,
        week_end_date DATE NOT NULL,
        review_date DATE,
        review_data VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        agent_name VARCHAR,
        agent_version VARCHAR
    )
"""


def _review_data(week_label: str, red_count: int) -> dict:
    """Build a representative review_data payload (verdict, periodization, ...)."""
    verdict = [
        {
            "date": "2026-06-16",
            "session": "Tempo",
            "rating": "✅",
            "comment": "狙い通りのテンポ走でした。",
        },
        {
            "date": "2026-06-18",
            "session": "Easy",
            "rating": "🟡",
            "comment": "心拍がやや高めでした。",
        },
    ]
    verdict += [
        {
            "date": "2026-06-20",
            "session": "Anaerobic",
            "rating": "🔴",
            "comment": "強度過多に注意してください。",
        }
        for _ in range(red_count)
    ]
    return {
        "plan_week_start": None,
        "actuals_week_start": None,
        "this_week": {
            "volume_km": 35.5,
            "run_count": 4,
            "hr_discipline": "Zone 2 中心で良好でした。",
            "highlights": ["週末ロング走を完遂"],
        },
        "garmin_next_week": [
            {"date": "2026-06-23", "title": "Tempo", "type": "fbtAdaptiveWorkout"},
        ],
        "periodization": {
            "weeks_to_a_race": None,
            "a_race": "さいたまマラソン",
            "weeks_to_b_race": 17,
            "b_race": "新潟シティマラソン",
            "expected_phase": "有酸素ベース構築期",
            "garmin_phase": "ベース期",
            "gap": "強度がやや先行気味です。",
        },
        "verdict": verdict,
        "goal_alignment": f"{week_label} は目標方針におおむね沿っています。",
        "recommendations": ["Z2を維持する（HR 135-145bpm）", "ロング走を1本入れる"],
        "overall": f"{week_label} は順調に積み上げられた良い週でした。",
    }


# (week_start_date, week_end_date, review_date, week_label, red_count)
_WEEKLY_REVIEW_ROWS = [
    ("2026-06-01", "2026-06-07", "2026-06-08", "6/1週", 1),
    ("2026-06-08", "2026-06-14", "2026-06-15", "6/8週", 0),
    ("2026-06-15", "2026-06-21", "2026-06-22", "6/15週", 2),
]


def _insert_weekly_reviews(conn: duckdb.DuckDBPyConnection) -> None:
    for idx, (start, end, review_date, label, red) in enumerate(
        _WEEKLY_REVIEW_ROWS, start=1
    ):
        conn.execute(
            "INSERT INTO weekly_reviews ("
            "review_id, user_id, week_start_date, week_end_date, review_date,"
            " review_data, agent_name, agent_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                idx,
                "default",
                start,
                end,
                review_date,
                json.dumps(_review_data(label, red), ensure_ascii=False),
                "weekly-review",
                "1.0",
            ],
        )


@pytest.fixture
def weekly_reviews_db_path(tmp_path: Path) -> Path:
    """DuckDB with weekly_reviews table populated (3 weeks, June 2026)."""
    db_path = tmp_path / "test_garmin_web_weekly_reviews.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_WEEKLY_REVIEWS)
        _insert_weekly_reviews(conn)
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_weekly_reviews_db_path(tmp_path: Path) -> Path:
    """DuckDB with an empty weekly_reviews table."""
    db_path = tmp_path / "test_garmin_web_weekly_reviews_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_WEEKLY_REVIEWS)
    finally:
        conn.close()
    return db_path


# --- Race readiness page fixtures (Issue #362) -------------------------
# RaceReader.get_race_readiness (#356) aggregates current VDOT (via
# FitnessAssessor: needs recent `activities` + `vo2_max`), the active race goal
# (`athlete_goals`), VDOT predictions, and a goal-progress block. Dates are
# computed relative to today so the activities always fall inside the default
# 8-week lookback window and the goal stays in the future.


def _build_race_readiness_db(db_path: Path, *, with_goal: bool) -> Path:
    """Create a race-readiness DB (activities + vo2_max [+ optional goal])."""
    today = _dt.date.today()
    recent_dates = [
        (today - _dt.timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in (3, 10, 17)
    ]
    future_race_date = (today + _dt.timedelta(days=180)).strftime("%Y-%m-%d")

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_VO2_MAX)
        conn.execute(_CREATE_HEART_RATE_ZONES)
        # FitnessAssessor reads hr_efficiency.training_type; left empty here.
        conn.execute(
            "CREATE TABLE hr_efficiency ("
            "activity_id BIGINT PRIMARY KEY, training_type VARCHAR)"
        )
        _create_goal_tables(conn)

        activity_rows = [
            (9000003001, recent_dates[0], "Tempo Run", 10.0, 2700, 270.0, 158),
            (9000003002, recent_dates[1], "Easy Run", 8.0, 2880, 360.0, 140),
            (9000003003, recent_dates[2], "Long Run", 16.0, 6240, 390.0, 145),
        ]
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            activity_rows,
        )
        # vo2_max drives VDOT (FitnessAssessor prefers precise_value).
        conn.execute(
            "INSERT INTO vo2_max VALUES (?, ?, ?, ?, ?)",
            [9000003001, 52.0, 52.0, recent_dates[0], 5],
        )

        if with_goal:
            conn.execute(
                "INSERT INTO athlete_goals ("
                "goal_id, user_id, race_name, race_date, priority, goal_type,"
                " distance_km, target_time_seconds, status, notes"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    1,
                    "default",
                    "さいたまマラソン",
                    future_race_date,
                    "A",
                    "marathon",
                    42.195,
                    16200,  # 4:30:00
                    "active",
                    "サブ4.5メインターゲット",
                ],
            )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def race_readiness_db_path(tmp_path: Path) -> Path:
    """DuckDB with recent activities + vo2_max + an active (priority A) goal."""
    db_path = tmp_path / "test_garmin_web_race_readiness.duckdb"
    return _build_race_readiness_db(db_path, with_goal=True)


@pytest.fixture
def race_readiness_no_goal_db_path(tmp_path: Path) -> Path:
    """DuckDB with recent activities + vo2_max but no race goal rows."""
    db_path = tmp_path / "test_garmin_web_race_readiness_no_goal.duckdb"
    return _build_race_readiness_db(db_path, with_goal=False)


# --- Training load (ACWR) fixtures (Issue #363) ------------------------
# GarminDBReader.get_acwr / get_load_trend (#357) read only the `activities`
# table (sum of total_distance_km per day). ACWR = acute (last-7-day load) /
# chronic weekly average (last-28-day load / 4). Dates are relative to today so
# the acute/chronic windows always line up with the inserted runs.


def _build_training_load_db(db_path: Path, *, spike: bool) -> Path:
    """Create a training-load DB (activities only).

    Steady weeks give an optimal ACWR; ``spike`` front-loads the most recent
    week so acute >> chronic weekly average (ACWR > 1.5 -> high_risk).
    """
    today = _dt.date.today()

    def _at(days_ago: int) -> str:
        return (today - _dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")

    # Four trailing weeks. Each tuple: (days_ago, distance_km).
    if spike:
        # Acute (last 7d) = 50 km; prior 3 weeks = 10 km each.
        # chronic_total(28d) = 80 -> weekly 20 -> ACWR = 50 / 20 = 2.5.
        runs = [
            (1, 50.0),  # this week (acute)
            (8, 10.0),  # week -1
            (15, 10.0),  # week -2
            (22, 10.0),  # week -3
        ]
    else:
        # Steady ~20 km/week -> acute 20, chronic weekly 20 -> ACWR ~1.0.
        runs = [
            (1, 20.0),
            (8, 20.0),
            (15, 20.0),
            (22, 20.0),
        ]

    activity_rows = [
        (9000004000 + idx, _at(days_ago), "Run", km, int(km * 300), 300.0, 145)
        for idx, (days_ago, km) in enumerate(runs, start=1)
    ]

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            activity_rows,
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def training_load_db_path(tmp_path: Path) -> Path:
    """DuckDB with steady weekly load (optimal ACWR ~1.0)."""
    db_path = tmp_path / "test_garmin_web_training_load.duckdb"
    return _build_training_load_db(db_path, spike=False)


@pytest.fixture
def training_load_high_risk_db_path(tmp_path: Path) -> Path:
    """DuckDB with a recent volume spike (ACWR > 1.5 -> high_risk)."""
    db_path = tmp_path / "test_garmin_web_training_load_high_risk.duckdb"
    return _build_training_load_db(db_path, spike=True)


# --- Durability (cardiac-decoupling) fixtures (Issue #364) -------------
# DurabilityReader.get_durability_trend (#358) reads `activities`
# (total_distance_km / activity_date >= min_distance_km) plus
# `time_series_metrics` (heart_rate, speed, timestamp_s per seq_no). For each
# qualifying long run it splits the series at the timestamp midpoint and
# compares back-half vs front-half HR/speed efficiency. We synthesise two
# >=15 km long runs whose second half costs more HR per unit speed (positive
# decoupling) so the endpoint returns non-empty activities + a trend block.

_DURABILITY_RANGE = 600  # time-series rows per long run


def _insert_durability_series(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    *,
    front_hr: int,
    back_hr: int,
    front_speed: float,
    back_speed: float,
    front_gct: float,
    back_gct: float,
) -> None:
    """Insert a two-phase HR/speed/GCT series (front half then back half).

    seq_no/timestamp_s share i so the midpoint splits the series cleanly; the
    back half uses a higher HR and slightly lower speed to produce a positive
    decoupling_pct (fade), plus a higher ground-contact time to produce a
    positive gct_fade_pct (#368).
    """
    half = _DURABILITY_RANGE // 2
    conn.execute(
        "INSERT INTO time_series_metrics"
        f" SELECT {activity_id}, i, i,"
        f" CASE WHEN i < {half} THEN {front_hr} ELSE {back_hr} END,"
        f" CASE WHEN i < {half} THEN {front_speed} ELSE {back_speed} END,"
        " 170.0, NULL, NULL,"
        f" CASE WHEN i < {half} THEN {front_gct} ELSE {back_gct} END,"
        " NULL, NULL"
        f" FROM range({_DURABILITY_RANGE}) AS t(i)"
    )


# (activity_id, date, name, distance_km, front_hr, back_hr, front_spd, back_spd,
#  front_gct, back_gct)
_DURABILITY_LONG_RUNS = [
    (9000005001, "2025-10-05", "Long Run A", 18.0, 145, 156, 2.8, 2.7, 250.0, 258.0),
    (9000005002, "2025-10-19", "Long Run B", 21.0, 144, 153, 2.8, 2.72, 250.0, 268.0),
]


@pytest.fixture
def durability_db_path(tmp_path: Path) -> Path:
    """DuckDB with two >=15 km long runs whose second half decouples.

    Also includes a short run (8 km) that must be excluded by the default
    ``min_distance_km`` filter.
    """
    db_path = tmp_path / "test_garmin_web_durability.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_TIME_SERIES_METRICS)

        activity_rows = [
            (aid, date, name, km, int(km * 330), 330.0, front_hr)
            for aid, date, name, km, front_hr, _back_hr, _fs, _bs, _fg, _bg in (
                _DURABILITY_LONG_RUNS
            )
        ]
        # Short run that should be filtered out (< 15 km).
        activity_rows.append(
            (9000005003, "2025-10-12", "Short Run", 8.0, 2400, 300.0, 140)
        )
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            activity_rows,
        )

        for (
            aid,
            _date,
            _name,
            _km,
            front_hr,
            back_hr,
            front_spd,
            back_spd,
            front_gct,
            back_gct,
        ) in _DURABILITY_LONG_RUNS:
            _insert_durability_series(
                conn,
                aid,
                front_hr=front_hr,
                back_hr=back_hr,
                front_speed=front_spd,
                back_speed=back_spd,
                front_gct=front_gct,
                back_gct=back_gct,
            )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def durability_empty_db_path(tmp_path: Path) -> Path:
    """DuckDB with only short runs (< 15 km) -> no qualifying long runs."""
    db_path = tmp_path / "test_garmin_web_durability_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_TIME_SERIES_METRICS)
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (9000005101, "2025-10-05", "Easy Run", 8.0, 2400, 300.0, 140),
                (9000005102, "2025-10-12", "Easy Run", 6.0, 1800, 300.0, 138),
            ],
        )
    finally:
        conn.close()
    return db_path


# --- Recovery / body-composition fixtures (Issue #502) -----------------
# Mirror the daily_wellness schema (migrations/add_daily_wellness_table.py),
# the body_composition schema (db_writer.py) and the lactate_threshold FTP
# columns the body-composition reader joins for lean power-to-weight. The Web
# layer delegates to GarminDBReader (#499/#500/#501); data is written directly.

_CREATE_DAILY_WELLNESS = """
    CREATE TABLE daily_wellness (
        wellness_id INTEGER PRIMARY KEY,
        date DATE NOT NULL,
        resting_hr INTEGER,
        hrv_overnight_ms DOUBLE,
        hrv_status VARCHAR,
        hrv_baseline_low DOUBLE,
        hrv_baseline_high DOUBLE,
        sleep_seconds INTEGER,
        sleep_score INTEGER,
        training_readiness INTEGER,
        body_battery_high INTEGER,
        body_battery_low INTEGER,
        stress_avg INTEGER,
        source VARCHAR
    )
"""

_CREATE_BODY_COMPOSITION = """
    CREATE TABLE body_composition (
        measurement_id INTEGER PRIMARY KEY,
        date DATE NOT NULL,
        weight_kg DOUBLE,
        body_fat_percentage DOUBLE,
        muscle_mass_kg DOUBLE,
        bone_mass_kg DOUBLE,
        bmi DOUBLE,
        hydration_percentage DOUBLE,
        measurement_source VARCHAR
    )
"""

# FTP columns the body-composition reader reads for lean power-to-weight.
_CREATE_LACTATE_THRESHOLD_FTP = """
    CREATE TABLE lactate_threshold (
        activity_id BIGINT PRIMARY KEY,
        functional_threshold_power INTEGER,
        power_to_weight DOUBLE,
        date_power TIMESTAMP
    )
"""


def _recent_dates(n: int) -> list[str]:
    """``n`` ascending dates ending today, so they fall in the trailing window."""
    today = _dt.date.today()
    return [
        (today - _dt.timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(n - 1, -1, -1)
    ]


@pytest.fixture
def recovery_db_path(tmp_path: Path) -> Path:
    """DuckDB with daily_wellness rows over the trailing days.

    The most recent night is below the HRV baseline band twice in a row so the
    HRV under-recovery flag is exercised; readiness/sleep stay mid-to-high so
    the latest-day status is recommendable.
    """
    db_path = tmp_path / "test_garmin_web_recovery.duckdb"
    dates = _recent_dates(5)
    # (resting_hr, hrv_overnight_ms, hrv_low, hrv_high, sleep, readiness, bb_high)
    rows = [
        (48, 65.0, 55.0, 80.0, 82, 78, 90),
        (47, 68.0, 55.0, 80.0, 80, 80, 92),
        (49, 70.0, 55.0, 80.0, 78, 76, 88),
        (50, 52.0, 55.0, 80.0, 70, 70, 75),  # below baseline (night -1)
        (51, 50.0, 55.0, 80.0, 72, 72, 78),  # below baseline (latest night)
    ]
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_DAILY_WELLNESS)
        conn.executemany(
            "INSERT INTO daily_wellness ("
            "wellness_id, date, resting_hr, hrv_overnight_ms, hrv_status,"
            " hrv_baseline_low, hrv_baseline_high, sleep_score,"
            " training_readiness, body_battery_high"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    idx + 1,
                    dates[idx],
                    rhr,
                    hrv,
                    "balanced",
                    low,
                    high,
                    sleep,
                    readiness,
                    bb_high,
                )
                for idx, (
                    rhr,
                    hrv,
                    low,
                    high,
                    sleep,
                    readiness,
                    bb_high,
                ) in enumerate(rows)
            ],
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def body_composition_db_path(tmp_path: Path) -> Path:
    """DuckDB with body_composition rows (net weight loss) + an FTP row.

    Weight falls from 80.0 to 78.8 kg over the window with body fat dropping,
    so ``change`` reports a negative ``delta_weight``; the FTP row drives a
    non-null lean power-to-weight.
    """
    db_path = tmp_path / "test_garmin_web_body_composition.duckdb"
    dates = _recent_dates(4)
    # (weight_kg, body_fat_percentage)
    measurements = [
        (80.0, 22.0),
        (79.5, 21.6),
        (79.1, 21.2),
        (78.8, 20.8),
    ]
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_BODY_COMPOSITION)
        conn.execute(_CREATE_LACTATE_THRESHOLD_FTP)
        conn.executemany(
            "INSERT INTO body_composition ("
            "measurement_id, date, weight_kg, body_fat_percentage"
            ") VALUES (?, ?, ?, ?)",
            [
                (idx + 1, dates[idx], weight, fat)
                for idx, (weight, fat) in enumerate(measurements)
            ],
        )
        conn.execute(
            "INSERT INTO lactate_threshold ("
            "activity_id, functional_threshold_power, power_to_weight, date_power"
            ") VALUES (?, ?, ?, ?)",
            [9000006001, 250, 3.1, f"{dates[-1]} 06:30:00"],
        )
    finally:
        conn.close()
    return db_path


@pytest.fixture
def empty_recovery_db_path(tmp_path: Path) -> Path:
    """DuckDB with empty daily_wellness / body_composition / FTP tables."""
    db_path = tmp_path / "test_garmin_web_recovery_empty.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_DAILY_WELLNESS)
        conn.execute(_CREATE_BODY_COMPOSITION)
        conn.execute(_CREATE_LACTATE_THRESHOLD_FTP)
    finally:
        conn.close()
    return db_path


# --- Heat-adjusted trend fixtures (Issue #551) ------------------------------
# The heat-adjustment model (Issue #549) re-reads avg_heart_rate /
# avg_pace_seconds_per_km / temp_celsius / activity_date from the activities
# table via GarminDBReader, so the fixture DB must expose those columns and be
# file-backed (the query resolves the file from the connection and re-opens it
# read-only). MIN_FIT_ACTIVITIES is 10, so the happy fixture seeds 12 rows with
# temperature spread to keep the regression well-conditioned.

_CREATE_HEAT_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE NOT NULL,
        avg_heart_rate INTEGER,
        avg_pace_seconds_per_km DOUBLE,
        temp_celsius DOUBLE
    )
"""


def _heat_rows(dates: list[str]) -> list[tuple[int, str, int, float, float]]:
    """Synthesize (id, date, hr, pace, temp) rows with a +0.35 bpm/°C signal."""
    rows: list[tuple[int, str, int, float, float]] = []
    for i, day in enumerate(dates):
        temp = 8.0 + (i % 6) * 5.0  # 8..33 °C, crossing the 15 °C hinge
        pace = 360.0 + (i % 3) * 8.0
        hinge = max(temp - 15.0, 0.0)
        hr = int(round(140 + 0.35 * hinge + (i % 2)))
        rows.append((9000007000 + i, day, hr, pace, temp))
    return rows


def _seed_heat_db(db_path: Path, rows: list[tuple]) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_HEAT_ACTIVITIES)
        if rows:
            conn.executemany(
                "INSERT INTO activities VALUES (?, ?, ?, ?, ?)",
                rows,
            )
    finally:
        conn.close()


@pytest.fixture
def heat_conn_happy(tmp_path: Path):
    """Read-only file-backed conn with 12 heat-varying runs (2025 H1)."""
    db_path = tmp_path / "test_garmin_web_heat.duckdb"
    dates = [
        (_dt.date(2025, 1, 6) + _dt.timedelta(days=14 * i)).isoformat()
        for i in range(12)
    ]
    _seed_heat_db(db_path, _heat_rows(dates))
    conn = duckdb.connect(str(db_path), read_only=True)
    yield conn
    conn.close()


@pytest.fixture
def heat_conn_insufficient(tmp_path: Path):
    """Read-only file-backed conn with a single run (below the fit minimum)."""
    db_path = tmp_path / "test_garmin_web_heat_one.duckdb"
    _seed_heat_db(db_path, _heat_rows(["2025-03-01"]))
    conn = duckdb.connect(str(db_path), read_only=True)
    yield conn
    conn.close()


@pytest.fixture
def heat_db_path(tmp_path: Path) -> Path:
    """File DuckDB with 12 heat-varying runs within the trailing year."""
    db_path = tmp_path / "test_garmin_web_heat_api.duckdb"
    today = _dt.date.today()
    dates = [(today - _dt.timedelta(days=20 * i + 5)).isoformat() for i in range(12)]
    _seed_heat_db(db_path, _heat_rows(dates))
    return db_path
