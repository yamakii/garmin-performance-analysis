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
