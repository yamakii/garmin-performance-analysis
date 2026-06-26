"""DB-backed tests for garmin_web.queries.objective_fitness.

These exercise the query against km-unit ``splits.distance`` rows (how the
production DuckDB stores split distance — 1.0 == a 1 km lap). They guard the
km->m conversion the query must apply before feeding the meters-based
``best_contiguous_segment`` extractor: without it every run yields 0 best
efforts and every quarter is dropped (Epic #526 #565 regression).
"""

import duckdb
import pytest

from garmin_web.queries.objective_fitness import get_quarterly_critical_speed

_CREATE_ACTIVITIES = """
    CREATE TABLE activities (
        activity_id BIGINT,
        activity_date DATE
    )
"""
_CREATE_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE
    )
"""


def _km_unit_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with two Q2-2026 runs whose splits are 1 km laps."""
    conn = duckdb.connect(":memory:")
    conn.execute(_CREATE_ACTIVITIES)
    conn.execute(_CREATE_SPLITS)
    conn.executemany(
        "INSERT INTO activities VALUES (?, ?)",
        [(9100000001, "2026-04-01"), (9100000002, "2026-05-01")],
    )
    # distance is in KM (1.0 == 1 km lap), like the production extractor stores.
    run1 = [(9100000001, i, 1.0, 370.0) for i in range(10)]  # 10 km @ 6:10/km
    run2 = [(9100000002, i, 1.0, 360.0) for i in range(6)]  # 6 km @ 6:00/km
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?)",
        run1 + run2,
    )
    return conn


@pytest.mark.integration
def test_get_quarterly_critical_speed_km_unit_splits_nonempty():
    """km-unit splits must yield a fittable quarter (regression for the km->m bug)."""
    conn = _km_unit_conn()
    try:
        result = get_quarterly_critical_speed(conn)
    finally:
        conn.close()

    assert result, "km-unit splits produced no quarters (km->m conversion missing)"
    q2 = result[0]
    assert q2["quarter"] == "2026-Q2"
    assert q2["n"] >= 2
    assert 1.0 < q2["cs_mps"] < 6.0
    assert 200.0 < q2["cs_pace_sec_per_km"] < 600.0
    assert "threshold-anchored" in q2["label"]


@pytest.mark.integration
def test_get_quarterly_critical_speed_omits_d_prime():
    """D' is invalid here and must never be surfaced in the query output."""
    conn = _km_unit_conn()
    try:
        result = get_quarterly_critical_speed(conn)
    finally:
        conn.close()

    assert result
    for quarter in result:
        assert "d_prime" not in quarter
        assert "d_prime_m" not in quarter


@pytest.mark.integration
def test_get_quarterly_critical_speed_empty_db():
    """No splits / no activities -> empty list, no exception."""
    conn = duckdb.connect(":memory:")
    conn.execute(_CREATE_ACTIVITIES)
    conn.execute(_CREATE_SPLITS)
    try:
        assert get_quarterly_critical_speed(conn) == []
    finally:
        conn.close()
