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
        latitude DOUBLE,
        longitude DOUBLE,
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
        conn.execute(_CREATE_ACTIVITIES)
        conn.execute(_CREATE_SPLITS)
        conn.execute(_CREATE_FORM_EFFICIENCY)
        conn.execute(_CREATE_HEART_RATE_ZONES)
        conn.execute(_CREATE_PERFORMANCE_TRENDS)
        conn.execute(_CREATE_FORM_EVALUATIONS_DETAIL)
        conn.execute(_CREATE_VO2_MAX)
        conn.execute(_CREATE_LACTATE_THRESHOLD)
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
            " 35.6 + i * 1e-5, 139.7 + i * 1e-5"
            " FROM range(2000) AS t(i)"
        )
        conn.execute(
            "INSERT INTO time_series_metrics"
            f" SELECT {PARTIAL_ACTIVITY_ID}, i, i, 135 + i % 10, 2.6, 168.0,"
            " NULL, NULL"
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
